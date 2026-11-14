package mcport;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.Type;

/**
 * HostBridge —— 宿主侧兼容桥（与 McPortRuntime 正交的第二条路）。
 *
 * McPortRuntime 改【mod 侧】：把旧引用重命名到新符号，只能解决纯改名 (RENAME)。
 * 当上游连签名都改了 (SIGCHG —— 8 份热门 mod 工单里 173 条)，重命名无能为力，
 * 因为 JVM 按 类名+成员名+描述符 精确链接 (JVMS 5.4.3)：名字对上、描述符不对，
 * 一样抛 NoSuchMethodError。
 *
 * HostBridge 反过来改【宿主侧】：在目标版本游戏类【定义之前】注入一个旧签名的
 * "桥方法"，方法体把调用转发给一个普通人写的静态适配器方法。于是旧 mod 的引用
 * 能链接上，且 mod 二进制一字节不改（demo 场景 E2 用 sha1 自证）。
 *
 * 为什么桥体不自动生成：旧参数如何变成新调用是【语义】，机械推导不出来。
 * demo 场景 E2 里源版本 getBlock(1,2,3)=42，而新版 getBlockState(BlockPos)=1+2+3=6，
 * 直观展示"名字+描述符对上了，行为仍然变了" —— 这正是 §1 第 3 层语义漂移。
 * 所以本组件只做可判定的机械部分（生成转发壳），语义放在 adapter 的普通 Java
 * 源码里，可编译、可测试、可读、可 code review。
 *
 * 为什么必须 premain / 类定义前：HotSpot 的 retransformClasses 不允许改 schema。
 * 实测（demo 场景 E3，JDK 17.0.20.1）：对已加载的类重定义并新增方法 ->
 *   UnsupportedOperationException: class redefinition failed: attempted to add a method
 * 因此 transform 只在 redefined == null (pre-define) 时注入；类一旦已加载，
 * 一律拒绝并 fail-loud，绝不制造"以为加上了"的错觉。
 * 这与 JEP 451 的结论一致：长期合法的寄生方式只有启动期 -javaagent。
 *
 * 规则 (TSV, -Dmcport.bridge=<file>)，每行 6 列：
 *   owner  oldName  oldDesc  kind  adapterClass  adapterMethod
 *   kind = virtual（注入实例方法，adapter 首参为宿主 this）
 *        | static （注入静态方法，adapter 无 this）
 *   adapter 描述符自动推导（不让人手写，减少错）：
 *     virtual -> (L{owner}; + oldDesc 参数 + ) + oldDesc 返回
 *     static  -> (        + oldDesc 参数 + ) + oldDesc 返回
 *   adapter 方法必须是 public static。<init>/<clinit> 明确不支持（fail-loud）。
 */
public final class HostBridge {

    /** 供 retransform 限制探针读取；正式功能不用它。 */
    public static Instrumentation inst;

    private static final Map<String, List<Rule>> BY_OWNER = new LinkedHashMap<>();

    private static final class Rule {
        String owner, oldName, oldDesc, adapterClass, adapterMethod, adapterDesc;
        boolean isStatic;
        Type[] args;
        Type ret;
    }

    public static void premain(String agentArgs, Instrumentation i) {
        inst = i;
        String path = System.getProperty("mcport.bridge", agentArgs == null ? "" : agentArgs);
        if (path.isBlank()) {
            // fail-loud：没有规则表就不启动，避免"看起来挂了 agent 其实什么都没做"。
            throw new IllegalStateException(
                    "[hostbridge] no -Dmcport.bridge=<spec>; refusing to start");
        }
        try {
            load(path);
        } catch (Exception e) {
            throw new IllegalStateException("[hostbridge] cannot load bridge spec " + path, e);
        }
        System.err.printf("[hostbridge] rules=%d owners=%s%n", count(), BY_OWNER.keySet());

        // 注意：不注册 canRetransform=true —— 本组件按设计只在类定义前工作。
        i.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String name, Class<?> redefined,
                                    ProtectionDomain pd, byte[] buf) {
                if (name == null || buf == null) return null;
                List<Rule> rules = BY_OWNER.get(name);
                if (rules == null || rules.isEmpty()) return null;
                if (redefined != null) {
                    System.err.println("[hostbridge] REFUSE retransform of already-loaded "
                            + name + ": adding a method changes the schema (HotSpot rejects it)");
                    return null;
                }
                try {
                    return weave(buf, rules);
                } catch (Throwable t) {
                    System.err.println("[hostbridge] FAILED to weave " + name + ": " + t);
                    return null;   // 原样加载 -> 旧引用在链接期明确报错，不静默
                }
            }
        });
    }

    private static int count() {
        int n = 0;
        for (List<Rule> l : BY_OWNER.values()) n += l.size();
        return n;
    }

    private static void load(String path) throws IOException {
        for (String line : Files.readAllLines(Paths.get(path))) {
            String s = line.trim();
            if (s.isEmpty() || s.startsWith("#")) continue;
            String[] p = s.split("\t", -1);
            if (p.length != 6) throw new IOException("rule needs 6 tab-separated columns: " + line);
            Rule r = new Rule();
            r.owner = p[0].trim();
            r.oldName = p[1].trim();
            r.oldDesc = p[2].trim();
            String kind = p[3].trim();
            r.adapterClass = p[4].trim();
            r.adapterMethod = p[5].trim();
            if (r.oldName.equals("<init>") || r.oldName.equals("<clinit>"))
                throw new IOException("cannot bridge a constructor/initializer: " + line);
            if (kind.equals("static")) r.isStatic = true;
            else if (kind.equals("virtual")) r.isStatic = false;
            else throw new IOException("kind must be virtual|static: " + line);
            if (!r.oldDesc.startsWith("("))
                throw new IOException("bad method descriptor: " + line);
            Type m = Type.getMethodType(r.oldDesc);
            r.args = m.getArgumentTypes();
            r.ret = m.getReturnType();

            StringBuilder sb = new StringBuilder("(");
            if (!r.isStatic) sb.append('L').append(r.owner).append(';');
            for (Type a : r.args) sb.append(a.getDescriptor());
            sb.append(')').append(r.ret.getDescriptor());
            r.adapterDesc = sb.toString();

            BY_OWNER.computeIfAbsent(r.owner, k -> new ArrayList<>()).add(r);
        }
        if (BY_OWNER.isEmpty()) throw new IOException("bridge spec has no rules: " + path);
    }

    private static byte[] weave(byte[] buf, List<Rule> rules) {
        ClassReader cr = new ClassReader(buf);
        // 收集宿主已有方法，避免注入重复签名（会 VerifyError）。
        final Set<String> existing = new HashSet<>();
        cr.accept(new ClassVisitor(Opcodes.ASM9) {
            @Override
            public MethodVisitor visitMethod(int a, String n, String d, String sig, String[] ex) {
                existing.add(n + d);
                return null;
            }
        }, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);

        ClassWriter cw = new ClassWriter(cr, ClassWriter.COMPUTE_MAXS);
        cr.accept(new ClassVisitor(Opcodes.ASM9, cw) {
            @Override
            public void visitEnd() {
                for (Rule r : rules) {
                    if (existing.contains(r.oldName + r.oldDesc)) {
                        System.err.println("[hostbridge] skip " + r.owner + "." + r.oldName
                                + r.oldDesc + " : host already declares it");
                        continue;
                    }
                    int acc = Opcodes.ACC_PUBLIC | (r.isStatic ? Opcodes.ACC_STATIC : 0);
                    MethodVisitor mv = super.visitMethod(acc, r.oldName, r.oldDesc, null, null);
                    mv.visitCode();
                    int slot = 0;
                    if (!r.isStatic) {
                        mv.visitVarInsn(Opcodes.ALOAD, 0);        // this -> adapter 首参
                        slot = 1;
                    }
                    for (Type a : r.args) {
                        mv.visitVarInsn(a.getOpcode(Opcodes.ILOAD), slot);
                        slot += a.getSize();                       // long/double 占 2 槽
                    }
                    mv.visitMethodInsn(Opcodes.INVOKESTATIC, r.adapterClass,
                            r.adapterMethod, r.adapterDesc, false);
                    if (r.ret.getSort() == Type.VOID) mv.visitInsn(Opcodes.RETURN);
                    else mv.visitInsn(r.ret.getOpcode(Opcodes.IRETURN));
                    mv.visitMaxs(0, 0);
                    mv.visitEnd();
                }
                super.visitEnd();
            }
        }, 0);
        return cw.toByteArray();
    }
}
