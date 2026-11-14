package mcport;

import org.objectweb.asm.Type;
import org.objectweb.asm.tree.*;
import java.util.*;
import java.util.regex.*;

/**
 * MixinRewriter —— 改写 Mixin 注解里的**字符串值**。
 *
 * 为什么 ClassRemapper 不够：@Mixin(targets=...)、@Inject(method=...)、
 * @Redirect(method=...)、@Accessor("field_N") 等把目标符号编码成 String / String[]，
 * 而不是常量池里的 CONSTANT_Methodref。ASM 的 AnnotationRemapper 只处理 Type/枚举
 * 描述符，对普通 String 原样放行。于是字节码重映射后注解里仍残留 intermediary token
 * （实测 14 个 1.21.1 mod 共 3721 个），静态 LinkCheck 看不见，运行期 Mixin 才炸。
 *
 * intermediary 命名空间是扁平的（net.minecraft.class_N / class_N$class_M），
 * 因此可以用精确正则匹配，不必猜包名结构。
 *
 * 改写策略（保守）：
 *   - 类 token：net[./]minecraft[./]class_N[$class_M] -> 26.x 真实名
 *   - 全限定成员：L<owner>;<name><desc>  -> 用原始(intermediary)owner/name/desc 查映射，
 *     输出时再把 owner 与 desc 里的类 token 换成真实名
 *   - 裸方法：method_N(desc) -> 用 @Mixin 的 targets 作为 owner 查（含继承解析）
 *   - 裸字段/方法名：field_N / method_N -> 按 (owner,name) 唯一候选查
 *   - 查不到一律保留原值（fail-loud，交给 Mixin 框架明确报错）
 *
 * 明确**不做**的事（见 REPORT §8）：不改 @Shadow/@Invoker/@Accessor 方法的声明名。
 * 因为 mod 自身代码里对这些方法的调用点 owner 是 mod 类、不在映射表内，只改声明
 * 会造成"声明改了、调用没改"的链接错误。这需要 refmap 或全符号表重写，属于另一层工作。
 */
public final class MixinRewriter {
    /** 扁平 intermediary 类名（含可选 $ 内部类），允许点分或斜杠包名。 */
    private static final Pattern CLASS_TOK = Pattern.compile(
        "(L?)((?:net[./]minecraft|com[./]mojang)[./]class_[0-9]+(?:\\$class_[0-9]+)*)");
    /** Lowner;name(desc)ret —— Mixin 的 target 标准写法。 */
    private static final Pattern FULL = Pattern.compile(
        "^(L?)([A-Za-z0-9_$/.]+);([A-Za-z0-9_$<>]+)(\\([^)]*\\).+)$");
    /** owner.fieldName:desc（Mixin 的字段引用写法）。 */
    private static final Pattern FULL_FLD = Pattern.compile(
        "^(L?)([A-Za-z0-9_$/.]+);([A-Za-z0-9_$]+):(.+)$");
    /** method_N(desc)ret —— @Inject/@Redirect 的 method 数组元素。 */
    private static final Pattern NAME_DESC = Pattern.compile("^([A-Za-z0-9_$<>]+)(\\([^)]*\\).+)$");
    private static final Pattern BARE = Pattern.compile("^(method|field)_[0-9]+$");

    private final Mapping map;
    private final List<String> owners = new ArrayList<>();
    public long changed, unresolved;

    public MixinRewriter(Mapping map) { this.map = map; }

    /** 入口：在 ClassNode 上原地改写；调用方随后再过 ClassRemapper。 */
    public void rewrite(ClassNode cn) {
        owners.clear();
        if (cn.visibleAnnotations != null) collectMixin(cn.visibleAnnotations);
        if (cn.invisibleAnnotations != null) collectMixin(cn.invisibleAnnotations);   // @Mixin 是 CLASS retention
        if (cn.visibleAnnotations != null) values(cn.visibleAnnotations);
        if (cn.invisibleAnnotations != null) values(cn.invisibleAnnotations);
        if (cn.visibleTypeAnnotations != null) values(cn.visibleTypeAnnotations);
        if (cn.invisibleTypeAnnotations != null) values(cn.invisibleTypeAnnotations);
        if (cn.fields != null) for (FieldNode f : cn.fields) {
            if (f.visibleAnnotations != null) values(f.visibleAnnotations);
            if (f.invisibleAnnotations != null) values(f.invisibleAnnotations);
            if (f.visibleTypeAnnotations != null) values(f.visibleTypeAnnotations);
            if (f.invisibleTypeAnnotations != null) values(f.invisibleTypeAnnotations);
        }
        if (cn.methods != null) for (MethodNode mn : cn.methods) {
            if (mn.visibleAnnotations != null) values(mn.visibleAnnotations);
            if (mn.invisibleAnnotations != null) values(mn.invisibleAnnotations);
            if (mn.visibleTypeAnnotations != null) values(mn.visibleTypeAnnotations);
            if (mn.invisibleTypeAnnotations != null) values(mn.invisibleTypeAnnotations);
            if (mn.visibleParameterAnnotations != null) for (List<AnnotationNode> l : mn.visibleParameterAnnotations) if (l != null) values(l);
            if (mn.invisibleParameterAnnotations != null) for (List<AnnotationNode> l : mn.invisibleParameterAnnotations) if (l != null) values(l);
            if (mn.visibleLocalVariableAnnotations != null) values(mn.visibleLocalVariableAnnotations);
            if (mn.invisibleLocalVariableAnnotations != null) values(mn.invisibleLocalVariableAnnotations);
            if (mn.instructions != null) for (AbstractInsnNode ins : mn.instructions) {
                if (ins instanceof InvokeDynamicInsnNode) {
                    InvokeDynamicInsnNode d = (InvokeDynamicInsnNode) ins;
                    for (int i = 0; i < d.bsmArgs.length; i++) {
                        Object o = d.bsmArgs[i];
                        if (o instanceof String) d.bsmArgs[i] = rewrite((String) o);
                        else if (o instanceof Type) d.bsmArgs[i] = mapType((Type) o);
                    }
                }
            }
        }
    }

    private void collectMixin(List<AnnotationNode> anns) {
        for (AnnotationNode a : anns) {
            if (a == null || a.desc == null || !a.desc.contains("asm/mixin/Mixin")) continue;
            if (a.values == null) continue;
            for (int i = 0; i < a.values.size(); i += 2) {
                Object v = a.values.get(i + 1);
                if (v instanceof List) for (Object o : (List<?>) v) addOwner(o);
                else addOwner(v);
            }
        }
    }
    private void addOwner(Object o) {
        String s = null;
        if (o instanceof Type) s = ((Type) o).getInternalName();
        else if (o instanceof String) s = (String) o;
        if (s == null) return;
        if (s.startsWith("L") && s.endsWith(";")) s = s.substring(1, s.length() - 1);
        s = s.replace('.', '/');
        if (s.contains("class_")) owners.add(s);
    }

    private void values(List<? extends AnnotationNode> anns) {
        for (AnnotationNode a : anns) {
            if (a == null || a.values == null) continue;
            for (int i = 1; i < a.values.size(); i += 2) {
                a.values.set(i, value(a.values.get(i)));
            }
        }
    }
    private Object value(Object o) {
        if (o instanceof String) return rewrite((String) o);
        if (o instanceof List) {
            List<Object> l = new ArrayList<>();
            for (Object x : (List<?>) o) l.add(value(x));
            return l;
        }
        if (o instanceof Type) return mapType((Type) o);
        if (o instanceof AnnotationNode) { values(Collections.singletonList((AnnotationNode) o)); return o; }
        return o;
    }
    private Type mapType(Type t) {
        if (t.getSort() != Type.OBJECT && t.getSort() != Type.ARRAY) return t;
        String d = t.getDescriptor();
        String n = mapTypes(d);
        return n.equals(d) ? t : Type.getType(n);
    }

    /** 把字符串里所有 intermediary 类 token 换成真实名（点分形式保持点分）。 */
    public String mapTypes(String s) {
        Matcher m = CLASS_TOK.matcher(s);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            String tok = m.group(2);
            String key = tok.replace('.', '/');
            String real = map.mapClass(key);
            if (real.equals(key)) { m.appendReplacement(sb, Matcher.quoteReplacement(m.group(0))); continue; }
            boolean dotted = tok.contains("net.minecraft.") || tok.contains("com.mojang.");
            String out = dotted ? real.replace('/', '.') : real;
            m.appendReplacement(sb, Matcher.quoteReplacement(m.group(1) + out));
        }
        m.appendTail(sb);
        return sb.toString();
    }

    public String rewrite(String s) {
        if (s == null || s.isEmpty()) return s;
        if (!(s.contains("class_") || s.contains("method_") || s.contains("field_"))) return s;
        String out = null;

        Matcher fm = FULL.matcher(s);
        if (fm.matches()) {
            String owner = fm.group(2).replace('.', '/');
            String name = fm.group(3), desc = fm.group(4);
            out = "L" + map.mapClass(owner) + ";" + member("M", owner, name, desc) + mapTypes(desc);
        } else {
            Matcher ff = FULL_FLD.matcher(s);
            if (ff.matches()) {
                String owner = ff.group(2).replace('.', '/');
                String name = ff.group(3), desc = ff.group(4);
                out = "L" + map.mapClass(owner) + ";" + member("F", owner, name, desc) + ":" + mapTypes(desc);
            } else {
                Matcher nd = NAME_DESC.matcher(s);
                if (nd.matches()) {
                    out = member("M", null, nd.group(1), nd.group(2)) + mapTypes(nd.group(2));
                } else if (BARE.matcher(s).matches()) {
                    String kind = s.startsWith("method_") ? "M" : "F";
                    out = member(kind, null, s, null);
                } else {
                    out = mapTypes(s);
                }
            }
        }
        if (!out.equals(s)) changed++; else if (hasInter(out)) unresolved++;
        return out;
    }

    private String member(String kind, String owner, String name, String desc) {
        if (!(name.startsWith("method_") || name.startsWith("field_"))) return name;
        String r = null;
        if (owner != null && desc != null)
            r = kind.equals("M") ? map.methodName(owner, name, desc) : map.fieldName(owner, name, desc);
        if (r == null && desc != null) {
            for (String o : owners) {
                r = kind.equals("M") ? map.methodName(o, name, desc) : map.fieldName(o, name, desc);
                if (r != null) break;
            }
        }
        if (r == null) {
            for (String o : owners) {
                r = map.memberByOwnerName(kind, o, name);
                if (r != null) break;
            }
        }
        if (r == null && owner != null) r = map.memberByOwnerName(kind, owner, name);
        return r == null ? name : r;
    }
    static boolean hasInter(String s) {
        return s.contains("class_") || s.contains("method_") || s.contains("field_");
    }
}
