package mcport;

import org.objectweb.asm.commons.Remapper;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

/**
 * McPort 映射表的唯一实现（single source of truth）。
 *
 * 离线 RemapTool 与启动期 McPortRuntime 都必须只用这个类，不要再各自复制一份
 * load()/lookup()：本项目已经踩过一次「两套过滤逻辑漂移」的坑 —— LinkCheck 的
 * main() 与 batch() 各写一遍 net/minecraft 前缀判断，改了一处漏了另一处，
 * 结果把 26.x 的静态可解析率从 62.3% 虚报成 68.0%。
 *
 * 支持 4 种行（由 mkmap.py / bridge.py / bridge26.py 产出）：
 *   C <interOwner> <realOwner>
 *   M <interOwner> <interDesc> <interName> <realName>
 *   F <interOwner> <interDesc> <interName> <realName>
 *   S <interOwner> <interSuper> <iface1,iface2,...>       (可选，继承解析用)
 *
 * 继承解析为什么必须有：字节码里对成员的引用，owner 常常是子类/实现类，而
 * 映射表的 key 是**声明**该成员的接口或父类。例如 mod 调用
 * EditBox(class_342).method_25370()Z，但该方法声明在父接口 class_364 上。
 * 只做精确 owner 查找会漏改全部继承成员（实测 14 个 mod 里 491 条）。
 * ClassRemapper 传给 3 参数 mapMethodName 的 owner/descriptor 是**原始**
 * (intermediary 命名空间)值，与映射表 key 及 S 行同命名空间，可直接匹配。
 *
 * 失败语义一律 fail-loud：查不到就返回原名，JVM 链接期会明确抛
 * NoSuchMethodError，绝不猜名字（猜错 = 静默错误行为）。
 */
public final class Mapping {
    private final Map<String, String> cls = new HashMap<>();
    private final Map<String, String> meth = new HashMap<>();
    private final Map<String, String> fld = new HashMap<>();
    private final Map<String, String> sup = new HashMap<>();
    private final Map<String, List<String>> ifs = new HashMap<>();
    /** (kind|owner|name) -> 候选真实名集合；供 Mixin @Accessor/@Invoker 这种没有描述符的注解用。 */
    private final Map<String, Set<String>> byOwnerName = new HashMap<>();
    private int nCls, nMeth, nFld, nSuper;
    private long nInheritedMeth, nInheritedFld;

    public void load(String path) throws IOException {
        cls.clear(); meth.clear(); fld.clear(); sup.clear(); ifs.clear(); byOwnerName.clear();
        nCls = nMeth = nFld = nSuper = 0;
        nInheritedMeth = nInheritedFld = 0;
        for (String line : Files.readAllLines(Paths.get(path))) {
            if (line.isEmpty() || line.charAt(0) == '#') continue;
            String[] p = line.split("\t", -1);
            switch (p[0]) {
                case "C": if (p.length >= 3) { cls.put(p[1], p[2]); nCls++; } break;
                case "M": if (p.length >= 5) {
                    meth.put(key(p[1], p[2], p[3]), p[4]); nMeth++;
                    byOwnerName.computeIfAbsent("M|" + p[1] + "|" + p[3], k -> new HashSet<>()).add(p[4]);
                } break;
                case "F": if (p.length >= 5) {
                    fld.put(key(p[1], p[2], p[3]), p[4]); nFld++;
                    byOwnerName.computeIfAbsent("F|" + p[1] + "|" + p[3], k -> new HashSet<>()).add(p[4]);
                } break;
                case "S":
                    nSuper++;
                    if (p.length > 2 && !p[2].isEmpty()) sup.put(p[1], p[2]);
                    if (p.length > 3 && !p[3].isEmpty())
                        ifs.put(p[1], Arrays.asList(p[3].split(",")));
                    break;
                default: break;   // 未知行忽略，便于向前兼容新行类型
            }
        }
    }

    private static String key(String owner, String desc, String name) {
        return owner + "|" + desc + "|" + name;
    }

    /**
     * 无描述符时按 (owner, name) 反查成员名。唯一候选才返回；
     * 多个不同候选（重载）返回 null —— 宁可 fail-loud 也不猜。
     */
    public String memberByOwnerName(String kind, String owner, String name) {
        Deque<String> q = new ArrayDeque<>();
        Set<String> seen = new HashSet<>();
        q.add(owner);
        boolean first = true;
        while (!q.isEmpty()) {
            String c = q.poll();
            if (c == null || !seen.add(c)) continue;
            if (!first) {
                Set<String> s = byOwnerName.get(kind + "|" + c + "|" + name);
                if (s != null && s.size() == 1) return s.iterator().next();
                if (s != null && s.size() > 1) return null;
            }
            first = false;
            String s0 = sup.get(c);
            if (s0 != null && !s0.isEmpty() && !s0.equals("java/lang/Object")) q.add(s0);
            List<String> i0 = ifs.get(c);
            if (i0 != null) for (String x : i0) if (x != null && !x.isEmpty()) q.add(x);
        }
        // 精确 owner 优先（上面 first 跳过了），补一次
        Set<String> s = byOwnerName.get(kind + "|" + owner + "|" + name);
        if (s != null && s.size() == 1) return s.iterator().next();
        return null;
    }

    public String mapClass(String internalName) {
        String r = cls.get(internalName);
        return r == null ? internalName : r;
    }

    /** 返回映射后名字或 null（供 Mixin 字符串改写等场景使用，不计继承计数）。 */
    public String methodName(String owner, String name, String desc) {
        return lookup(meth, owner, desc, name);
    }
    public String fieldName(String owner, String name, String desc) {
        return lookup(fld, owner, desc, name);
    }

    /** 精确查不到时沿 S 行的父类链 BFS；返回 null 表示找不到。 */
    private String lookup(Map<String, String> tab, String owner, String desc, String name) {
        String direct = tab.get(key(owner, desc, name));
        if (direct != null) return direct;
        // 只有出现在 S 表里的 MC 类才做继承查找：避免对 mod 自身/JDK 类做无用功或误改。
        if (!sup.containsKey(owner) && !ifs.containsKey(owner)) return null;
        Deque<String> q = new ArrayDeque<>();
        Set<String> seen = new HashSet<>();
        q.add(owner);
        boolean first = true;
        while (!q.isEmpty()) {
            String c = q.poll();
            if (c == null || !seen.add(c)) continue;
            if (!first) {
                String hit = tab.get(key(c, desc, name));
                if (hit != null) return hit;
            }
            first = false;
            String s = sup.get(c);
            if (s != null && !s.isEmpty() && !s.equals("java/lang/Object")) q.add(s);
            List<String> i = ifs.get(c);
            if (i != null) for (String x : i) if (x != null && !x.isEmpty()) q.add(x);
        }
        return null;
    }

    public String mapMethod(String owner, String name, String descriptor) {
        String r = methodName(owner, name, descriptor);
        if (r == null) return name;
        if (!meth.containsKey(key(owner, descriptor, name))) nInheritedMeth++;
        return r;
    }

    public String mapField(String owner, String name, String descriptor) {
        String r = fieldName(owner, name, descriptor);
        if (r == null) return name;
        if (!fld.containsKey(key(owner, descriptor, name))) nInheritedFld++;
        return r;
    }

    /** 离线工具与启动期 agent 共用的同一个 Remapper 实现。 */
    public Remapper remapper() {
        return new Remapper() {
            @Override public String map(String internalName) { return mapClass(internalName); }
            @Override public String mapMethodName(String owner, String name, String descriptor) {
                return mapMethod(owner, name, descriptor);
            }
            @Override public String mapFieldName(String owner, String name, String descriptor) {
                return mapField(owner, name, descriptor);
            }
        };
    }

    public String summary() {
        return String.format("class=%d method=%d field=%d super=%d", nCls, nMeth, nFld, nSuper);
    }
    public String inherited() {
        return String.format("%d methods, %d fields", nInheritedMeth, nInheritedFld);
    }
    public Set<String> classKeys() { return cls.keySet(); }
}
