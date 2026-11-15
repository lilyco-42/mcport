package mcport;

import org.objectweb.asm.*;
import org.objectweb.asm.signature.SignatureReader;
import org.objectweb.asm.signature.SignatureVisitor;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

/**
 * LinkCheck —— McPort 的"跨版本可解析性预言机"。
 *
 * 作用：在不启动游戏的离线阶段，判断一个 mod jar 里的每一个 Minecraft 成员引用
 * 在目标版本里是否还能解析。它模拟 JVMS §5.4.3 的符号引用解析流程（含父类链、
 * 接口默认方法），并把失败分成三类，对应三种不同的修复代价：
 *
 *   RESOLVE  目标版本里同名同描述符存在（含继承）        —— 零改动可用
 *   RENAME   同 (owner,desc) 在目标版本有唯一新名        —— 可自动重映射
 *   SIGCHG   同 (owner,name) 存在但描述符变了            —— 需生成桥接 shim
 *   MISSING  owner 或成员彻底消失                        —— 必须重实现
 *
 * 用法:
 *   java -cp mcport.jar:asm.jar mcport.LinkCheck \
 *        --decl decl-<target>.tsv --mod mod.jar [--map map.tsv] [--json report.json] [--refs-json refs.json]
 *
 *   --refs-json (§23) writes exact (kind,owner,name,desc,status) refs; ordinary --json
 *   details remain byte-identical, while quote/control chars are now valid JSON.
 *
 * 退出码: 0 = 全部 RESOLVE/RENAME 可自动处理; 2 = 存在 SIGCHG/MISSING 需人工介入。
 */
public class LinkCheck {

    static final Map<String, String> SUPER = new HashMap<>();
    static final Map<String, List<String>> IFACES = new HashMap<>();
    static final Set<String> CLASSES = new HashSet<>();
    /** decl 里出现过的 com/mojang/<pkg> 三级包 = 随 client jar 发布的游戏类包。
     *  用于把独立库类(DataFixerUpper/Brigadier/authlib/logging)从 MC 引用预言机豁免;
     *  由目标版本真实声明表自证, 不硬编码库清单(26.3 新增的 renderpearl 也能自动识别)。 */
    static final Set<String> GAME_MOJANG_PKGS = new HashSet<>();
    static final Map<String, Set<String>> METHODS = new HashMap<>(); // owner|name -> descs
    static final Map<String, Set<String>> FIELDS = new HashMap<>();  // owner|name -> descs
    static final Map<String, String> CLS_RENAME = new HashMap<>();
    static final Map<String, String> M_RENAME = new HashMap<>();  // owner|desc|old -> new
    static final Map<String, String> F_RENAME = new HashMap<>();
    /** §23: exact structured refs. Only collected when COLLECT_STRUCT is set (single-mod main). */
    static final List<String[]> STRUCT = new ArrayList<>();
    static boolean COLLECT_STRUCT = false;

    public static void main(String[] argv) throws Exception {
        String decl = null, mod = null, map = null, json = null, refsJson = null, mods = null, out = null;
        for (int i = 0; i < argv.length; i++) {
            switch (argv[i]) {
                case "--decl": decl = argv[++i]; break;
                case "--mod": mod = argv[++i]; break;
                case "--map": map = argv[++i]; break;
                case "--json": json = argv[++i]; break;
                case "--refs-json": refsJson = argv[++i]; break;
                case "--mods": mods = argv[++i]; break;
                case "--out": out = argv[++i]; break;
                default: break;
            }
        }
        if (mods != null) {
            if (decl == null) { System.err.println("need --decl with --mods"); System.exit(1); }
            loadDecl(decl);
            if (map != null) loadMap(map);
            System.err.printf("[linkcheck] target: %d classes, %d method keys, %d field keys%n",
                    CLASSES.size(), METHODS.size(), FIELDS.size());
            batch(mods, out);
            return;
        }
        if (decl == null || mod == null) { System.err.println("need --decl and --mod"); System.exit(1); }
        loadDecl(decl);
        if (map != null) loadMap(map);
        System.err.printf("[linkcheck] target: %d classes, %d method keys, %d field keys%n",
                CLASSES.size(), METHODS.size(), FIELDS.size());

        Set<String> mrefs = new TreeSet<>(), frefs = new TreeSet<>(), cref = new TreeSet<>();
        collect(mod, mrefs, frefs, cref);
        COLLECT_STRUCT = true;

        Map<String, List<String>> buckets = new LinkedHashMap<>();
        buckets.put("RESOLVE", new ArrayList<>());
        buckets.put("RENAME", new ArrayList<>());
        buckets.put("SIGCHG", new ArrayList<>());
        buckets.put("MISSING", new ArrayList<>());
        buckets.put("EXTERNAL", new ArrayList<>());

        int mcM = 0, mcF = 0;
        for (String r : mrefs) {
            Ref ref = Ref.method(r);
            if (!isGameRef(ref.owner)) continue;
            mcM++;
            classify(ref, true, buckets);
        }
        for (String r : frefs) {
            Ref ref = Ref.field(r);
            if (!isGameRef(ref.owner)) continue;
            mcF++;
            classify(ref, false, buckets);
        }

        int tot = mcM + mcF;
        int ok = buckets.get("RESOLVE").size(), rn = buckets.get("RENAME").size();
        int sg = buckets.get("SIGCHG").size(), ms = buckets.get("MISSING").size();
        int ex = buckets.get("EXTERNAL").size();
        System.out.printf("mod: %s%n", mod);
        System.out.printf("MC refs: %d method + %d field = %d%n", mcM, mcF, tot);
        pct("RESOLVE (works as-is)", ok, tot);
        pct("RENAME  (auto-fixable with map)", rn, tot);
        pct("SIGCHG  (needs adapter shim)", sg, tot);
        pct("MISSING (needs reimplementation)", ms, tot);
        if (ex > 0) pct("EXTERNAL (JDK-inherited, assumed ok)", ex, tot);
        int judged = tot - ex;   // EXTERNAL 不计入分母: JDK 侧签名不由 MC 版本决定
        System.out.printf("=> judged %d (excluding %d JDK-inherited)%n", judged, ex);
        System.out.printf("=> auto-fix ceiling: %.1f%% ; as-is survival: %.1f%%%n",
                100.0 * (ok + rn) / Math.max(1, judged), 100.0 * ok / Math.max(1, judged));

        if (json != null) writeJson(json, mod, tot, ok, rn, sg, ms, buckets);
        if (refsJson != null) writeRefsJson(refsJson, mod);
        System.exit((sg + ms) == 0 ? 0 : 2);
    }

    /** 26.1 起去混淆后, 游戏类分布在 net/minecraft/ 与 com/mojang/(blaze3d/realmsclient/math/...)。
     *  后者与本就存在的独立库类(DataFixerUpper/Brigadier/authlib/logging)共享前缀,
     *  故 isGameRef 只管"是否进入 MC 命名空间扫描", 库类在 classify() 里按
     *  GAME_MOJANG_PKGS 自证豁免为 EXTERNAL, 保持单一实现(见 §5 第 11、15 条)。 */
    static boolean isGameRef(String owner) {
        return owner.startsWith("net/minecraft/") || owner.startsWith("com/mojang/");
    }

    /** com/mojang/<pkg> 三级包; 非 com/mojang 返回 null。 */
    static String mojangPkg(String owner) {
        if (!owner.startsWith("com/mojang/")) return null;
        int i = owner.indexOf('/', "com/mojang/".length());
        return i < 0 ? owner : owner.substring(0, i);
    }
    static void noteMojangPkg(String owner) {
        String p = mojangPkg(owner);
        if (p != null) GAME_MOJANG_PKGS.add(p);
    }
    /** 外部独立库类: com/mojang 下、且三级包从未在目标版本 decl 出现过。 */
    static boolean isExternalMojangLib(String owner) {
        String p = mojangPkg(owner);
        return p != null && !GAME_MOJANG_PKGS.contains(p);
    }

    static void pct(String label, int n, int tot) {
        System.out.printf("  %-36s %5d (%5.1f%%)%n", label, n, 100.0 * n / Math.max(1, tot));
    }

    static final class Ref {
        String owner, name, desc;
        static Ref method(String r) { String[] p = r.split("\\|"); return m(p[0], p[1], p[2]); }
        static Ref field(String r) { String[] p = r.split("\\|"); return m(p[0], p[1], p[2]); }
        static Ref m(String o, String n, String d) { Ref x = new Ref(); x.owner = o; x.name = n; x.desc = d; return x; }
        public String toString() { return owner + "." + name + desc; }
    }

    /** 沿父类链查找；JVMS §5.4.3.3 的解析是先查本类、再查超类、再查超接口。 */
    static String[] findMember(Ref ref, boolean meth) {
        Map<String, Set<String>> tab = meth ? METHODS : FIELDS;
        Deque<String> q = new ArrayDeque<>();
        Set<String> seen = new HashSet<>();
        q.add(ref.owner);
        while (!q.isEmpty()) {
            String c = q.poll();
            if (c == null || !seen.add(c)) continue;
            Set<String> descs = tab.get(c + "|" + ref.name);
            if (descs != null && descs.contains(ref.desc)) return new String[]{c, ref.name, ref.desc};
            String s = SUPER.get(c);
            if (s != null) q.add(s);
            for (String i : IFACES.getOrDefault(c, Collections.emptyList())) if (i != null) q.add(i);
        }
        return null;
    }

    /** 同 (owner,name) 但描述符不同 -> 签名变更；用于区分 SIGCHG 与 MISSING。 */
    static String findSameNameOtherDesc(Ref ref, boolean meth) {
        Map<String, Set<String>> tab = meth ? METHODS : FIELDS;
        Deque<String> q = new ArrayDeque<>();
        Set<String> seen = new HashSet<>();
        q.add(ref.owner);
        while (!q.isEmpty()) {
            String c = q.poll();
            if (c == null || !seen.add(c)) continue;
            if (tab.containsKey(c + "|" + ref.name)) return c;
            String s = SUPER.get(c);
            if (s != null) q.add(s);
            for (String i : IFACES.getOrDefault(c, Collections.emptyList())) if (i != null) q.add(i);
        }
        return null;
    }

    /**
     * JDK 继承成员存根。decl 表覆盖 net/minecraft/* 与 client jar 内的 com/mojang/ 游戏类;
     * com/mojang/ 独立库类在 classify() 里被豁免为 EXTERNAL。但 mod 还会引用从 java/lang/*
     * 继承来的方法(toString/getClass/ordinal...); 不识别这些就会把合法引用误判成
     * "member gone"。控制组(目标==源版本)因此跑不到 100% —— 这是最好的哨兵。
     */
    static final Map<String, Set<String>> JDK = new HashMap<>();
    static {
        jdk("java/lang/Object", "toString()Ljava/lang/String;", "hashCode()I",
            "equals(Ljava/lang/Object;)Z", "getClass()Ljava/lang/Class;",
            "clone()Ljava/lang/Object;", "notify()V", "notifyAll()V", "wait()V",
            "wait(J)V", "finalize()V");
        jdk("java/lang/Enum", "ordinal()I", "name()Ljava/lang/String;",
            "compareTo(Ljava/lang/Enum;)I", "compareTo(Ljava/lang/Object;)I",
            "getDeclaringClass()Ljava/lang/Class;", "valueOf(Ljava/lang/Class;Ljava/lang/String;)Ljava/lang/Enum;");
        jdk("java/lang/Record", "toString()Ljava/lang/String;", "hashCode()I", "equals(Ljava/lang/Object;)Z");
        jdk("java/lang/Throwable", "getMessage()Ljava/lang/String;", "getCause()Ljava/lang/Throwable;",
            "printStackTrace()V", "toString()Ljava/lang/String;", "fillInStackTrace()Ljava/lang/Throwable;");
        jdk("java/lang/Iterable", "iterator()Ljava/util/Iterator;",
            "forEach(Ljava/util/function/Consumer;)V");
        jdk("java/lang/Number", "intValue()I", "longValue()J", "floatValue()F", "doubleValue()D");
        jdk("java/lang/Comparable", "compareTo(Ljava/lang/Object;)I");
        jdk("java/lang/AutoCloseable", "close()V");
        jdk("java/lang/Thread", "start()V", "run()V", "join()V", "interrupt()V", "isAlive()Z");
        jdk("java/util/Iterator", "hasNext()Z", "next()Ljava/lang/Object;", "remove()V");
        jdk("java/util/Collection", "size()I", "isEmpty()Z", "contains(Ljava/lang/Object;)Z",
            "add(Ljava/lang/Object;)Z", "remove(Ljava/lang/Object;)Z", "iterator()Ljava/util/Iterator;");
        jdk("java/util/List", "get(I)Ljava/lang/Object;", "size()I", "add(Ljava/lang/Object;)Z",
            "of()Ljava/util/List;", "stream()Ljava/util/stream/Stream;");
        jdk("java/util/Map", "get(Ljava/lang/Object;)Ljava/lang/Object;", "put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;",
            "containsKey(Ljava/lang/Object;)Z", "keySet()Ljava/util/Set;", "values()Ljava/util/Collection;",
            "entrySet()Ljava/util/Set;", "getOrDefault(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;");
        jdk("java/util/Set", "contains(Ljava/lang/Object;)Z", "add(Ljava/lang/Object;)Z", "size()I");
        jdk("java/util/stream/Stream", "filter(Ljava/util/function/Predicate;)Ljava/util/stream/Stream;",
            "map(Ljava/util/function/Function;)Ljava/util/stream/Stream;",
            "collect(Ljava/util/stream/Collector;)Ljava/lang/Object;", "toList()Ljava/util/List;");
    }
    static void jdk(String cls, String... members) {
        Set<String> set = JDK.computeIfAbsent(cls, k -> new HashSet<>());
        for (String m : members) set.add(m);
    }

    /** 成员是否是 JDK 继承来的(表外类)。 */
    static boolean jdkInherited(Ref ref, boolean meth) {
        if (!meth) return false;
        Map<String, Set<String>> tab = METHODS;
        Deque<String> q = new ArrayDeque<>();
        Set<String> seen = new HashSet<>();
        q.add(ref.owner);
        while (!q.isEmpty()) {
            String c = q.poll();
            if (c == null || !seen.add(c)) continue;
            boolean known = CLASSES.contains(c) || SUPER.containsKey(c);
            if (!known) {
                // 严格判定: 只有 JDK 存根表里明确声明了该 (name+desc) 才算 EXTERNAL。
                // 早期版本这里写 "c.startsWith(\"java/\") 就返回 true", 结果任何解不出来的
                // MC 成员都会顺着类链走到 java/lang/Object 然后被判 EXTERNAL —— 等于把
                // MISSING 全部洗白, 14.2% 的假阳性。判定必须靠成员, 不能靠类名前缀。
                Set<String> ms = JDK.get(c);
                if (ms != null && ms.contains(ref.name + ref.desc)) return true;
                continue;
            }
            String sup = SUPER.get(c);
            if (sup != null) q.add(sup);
            for (String i : IFACES.getOrDefault(c, Collections.emptyList())) if (i != null) q.add(i);
        }
        return false;
    }

    static void classify(Ref ref, boolean meth, Map<String, List<String>> out) {
        // §23: keep the legacy details text byte-identical, but also record the exact
        // (kind,owner,name,desc,status) tuple so downstream tools never have to guess
        // where owner.name+desc was split when an object-typed field name contains L.
        String status, text;
        if (findMember(ref, meth) != null) {
            status = "RESOLVE"; text = ref.toString();
        } else if (jdkInherited(ref, meth)) {
            status = "EXTERNAL"; text = ref + "  # inherited from JDK, assumed stable";
        } else if (isExternalMojangLib(ref.owner)) {
            // 目标==源的自检曾掉到 97.5%: com/mojang/ 下独立库类(不在任何版本 client jar)
            // 被当成"MC 游戏 API 消失"误判 MISSING。用 decl 自证的游戏包集合豁免为 EXTERNAL。
            status = "EXTERNAL"; text = ref + "  # external library, assumed stable";
        } else if (!CLASSES.contains(ref.owner) && !SUPER.containsKey(ref.owner)) {
            status = "MISSING"; text = ref + "  # owner class gone";
        } else {
            String key = ref.owner + "|" + ref.desc + "|" + ref.name;
            Map<String, String> rn = meth ? M_RENAME : F_RENAME;
            String same;
            if (rn.containsKey(key)) {
                status = "RENAME"; text = ref + "  -> " + rn.get(key);
            } else if ((same = findSameNameOtherDesc(ref, meth)) != null) {
                status = "SIGCHG"; text = ref + "  # name kept by " + same + ", descriptor changed";
            } else {
                status = "MISSING"; text = ref + "  # member gone";
            }
        }
        if (COLLECT_STRUCT) STRUCT.add(new String[]{meth ? "M" : "F", ref.owner, ref.name, ref.desc, status});
        out.get(status).add(text);
    }

    static void loadDecl(String path) throws IOException {
        int line = 0;
        for (String s : Files.readAllLines(Paths.get(path))) {
            if (s.isEmpty() || s.charAt(0) == '#') continue;
            String[] p = s.split("\t", -1);
            if (p.length > 1) noteMojangPkg(p[1]);
            switch (p[0]) {
                case "C": CLASSES.add(p[1]); break;
                case "S":
                    CLASSES.add(p[1]);
                    if (p.length > 2 && !p[2].isEmpty()) SUPER.put(p[1], p[2]);
                    if (p.length > 3 && !p[3].isEmpty()) IFACES.put(p[1], Arrays.asList(p[3].split(",")));
                    break;
                case "M": CLASSES.add(p[1]); METHODS.computeIfAbsent(p[1] + "|" + p[2], k -> new HashSet<>()).add(p[3]); break;
                case "F": CLASSES.add(p[1]); FIELDS.computeIfAbsent(p[1] + "|" + p[2], k -> new HashSet<>()).add(p[3]); break;
                default: break;
            }
            line++;
        }
    }

    static void loadMap(String path) throws IOException {
        for (String s : Files.readAllLines(Paths.get(path))) {
            if (s.isEmpty() || s.charAt(0) == '#') continue;
            String[] p = s.split("\t", -1);
            if (p[0].equals("C")) CLS_RENAME.put(p[1], p[2]);
            else if (p[0].equals("M")) M_RENAME.put(p[1] + "|" + p[2] + "|" + p[3], p[4]);
            else if (p[0].equals("F")) F_RENAME.put(p[1] + "|" + p[2] + "|" + p[3], p[4]);
        }
    }

    static void collect(String jar, Set<String> m, Set<String> f, Set<String> c) throws IOException {
        try (ZipInputStream zin = new ZipInputStream(new FileInputStream(jar))) {
            ZipEntry e;
            while ((e = zin.getNextEntry()) != null) {
                if (!e.getName().endsWith(".class")) continue;
                byte[] d = zin.readAllBytes();
                ClassReader cr = new ClassReader(d);
                cr.accept(new ClassVisitor(Opcodes.ASM9) {
                    @Override public void visit(int v, int acc, String name, String sig, String sup, String[] ifs) {
                        // 只登记父类本身; 不要伪造 <init>()V 引用 —— 真实的 super() 调用
                        // 在字节码里就是一条 invokespecial Methodref, 会自然被收集到。
                        // (伪造会让所有没有无参构造的 MC 类被误判成 SIGCHG。)
                        if (sup != null) c.add(sup);
                    }
                    @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] ex) {
                        return new MethodVisitor(Opcodes.ASM9) {
                            @Override public void visitMethodInsn(int op, String o, String n2, String d2, boolean itf) {
                                m.add(o + "|" + n2 + "|" + d2);
                                if (!d2.isEmpty()) for (String t : descTypes(d2)) c.add(t);
                            }
                            @Override public void visitFieldInsn(int op, String o, String n2, String d2) {
                                f.add(o + "|" + n2 + "|" + d2);
                                for (String t : descTypes(d2)) c.add(t);
                            }
                            @Override public void visitTypeInsn(int op, String t) { c.add(t); }
                            @Override public void visitLdcInsn(Object v) {
                                if (v instanceof Type) for (String t : descTypes(((Type) v).getDescriptor())) c.add(t);
                            }
                            @Override public void visitInvokeDynamicInsn(String n2, String d2, Handle bsm, Object... args) {
                                for (String t : descTypes(d2)) c.add(t);
                            }
                        };
                    }
                }, ClassReader.SKIP_DEBUG);
            }
        }
    }

    static List<String> descTypes(String d) {
        List<String> out = new ArrayList<>();
        int i = 0;
        while (i < d.length()) {
            char ch = d.charAt(i);
            if (ch == 'L') {
                int j = d.indexOf(';', i);
                if (j < 0) break;
                out.add(d.substring(i + 1, j));
                i = j + 1;
            } else i++;
        }
        return out;
    }

    static void writeJson(String path, String mod, int tot, int ok, int rn, int sg, int ms,
                          Map<String, List<String>> b) throws IOException {
        StringBuilder sb = new StringBuilder();
        // §23: q() escapes quotes/control chars too. Ordinary paths keep the
        // exact byte layout of the original writer (verified by the golden ticket).
        sb.append("{\"mod\":").append(q(mod)).append(",");
        sb.append("\"total\":").append(tot).append(",");
        sb.append("\"resolve\":").append(ok).append(",\"rename\":").append(rn)
          .append(",\"sigchg\":").append(sg).append(",\"missing\":").append(ms).append(",");
        sb.append("\"autoFixCeiling\":").append(Math.round(1000.0 * (ok + rn) / Math.max(1, tot)) / 10.0).append(",");
        sb.append("\"details\":{");
        boolean first = true;
        for (Map.Entry<String, List<String>> e : b.entrySet()) {
            if (!first) sb.append(",");
            first = false;
            sb.append("\"").append(e.getKey()).append("\":[");
            List<String> v = e.getValue();
            for (int i = 0; i < v.size(); i++) {
                if (i > 0) sb.append(",");
                sb.append(q(v.get(i)));
            }
            sb.append("]");
        }
        sb.append("}}");
        Files.writeString(Paths.get(path), sb.toString());
        System.err.println("[linkcheck] report -> " + path);
    }


    static final String QQ = String.valueOf((char) 34);
    /** §23: emit a complete JSON string, including control characters; a mod path
     *  may contain backslashes, quotes or newlines on a hostile filesystem. */
    static String q(String s) {
        StringBuilder b = new StringBuilder(QQ);
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '\\': b.append("\\\\"); break;
                case '"': b.append("\\\""); break;
                case '\b': b.append("\\b"); break;
                case '\f': b.append("\\f"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        return b.append(QQ).toString();
    }

    /** §23: deterministic structured refs. Legacy --json details stay untouched.
     *  q() makes every value valid JSON; refs are sorted by all five fields for
     *  reproducibility, while --json keeps its original byte-for-byte layout. */
    static void writeRefsJson(String path, String mod) throws IOException {
        List<String[]> v = new ArrayList<>(STRUCT);
        v.sort((x, y) -> {
            for (int i = 0; i < 5; i++) { int cmp = x[i].compareTo(y[i]); if (cmp != 0) return cmp; }
            return 0;
        });
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append(q("schema")).append(":1,");
        sb.append(q("tool")).append(":").append(q("mcport.LinkCheck")).append(",");
        sb.append(q("mod")).append(":").append(q(mod)).append(",");
        sb.append(q("ref_count")).append(":").append(v.size()).append(",");
        sb.append(q("refs")).append(":[");
        for (int i = 0; i < v.size(); i++) {
            String[] a = v.get(i);
            if (i > 0) sb.append(",");
            sb.append("{");
            sb.append(q("kind")).append(":").append(q(a[0])).append(",");
            sb.append(q("owner")).append(":").append(q(a[1])).append(",");
            sb.append(q("name")).append(":").append(q(a[2])).append(",");
            sb.append(q("desc")).append(":").append(q(a[3])).append(",");
            sb.append(q("status")).append(":").append(q(a[4]));
            sb.append("}");
        }
        sb.append("]}");
        Files.writeString(Paths.get(path), sb.toString());
        System.err.println("[linkcheck] structured refs -> " + path);
    }


    /** 对一个 jar 做一次完整判定，返回 {tot, ok, rn, sg, ms, ex, mcM, mcF}。 */
    static int[] analyze(String jar) {
        Set<String> mrefs = new TreeSet<>(), frefs = new TreeSet<>(), cref = new TreeSet<>();
        try { collect(jar, mrefs, frefs, cref); }
        catch (Exception e) { throw new RuntimeException("cannot read " + jar, e); }
        Map<String, List<String>> b = new LinkedHashMap<>();
        for (String k : new String[]{"RESOLVE", "RENAME", "SIGCHG", "MISSING", "EXTERNAL"}) b.put(k, new ArrayList<>());
        int mcM = 0, mcF = 0;
        for (String r : mrefs) { Ref ref = Ref.method(r); if (!isGameRef(ref.owner)) continue; mcM++; classify(ref, true, b); }
        for (String r : frefs) { Ref ref = Ref.field(r); if (!isGameRef(ref.owner)) continue; mcF++; classify(ref, false, b); }
        int tot = mcM + mcF;
        return new int[]{tot, b.get("RESOLVE").size(), b.get("RENAME").size(),
                b.get("SIGCHG").size(), b.get("MISSING").size(), b.get("EXTERNAL").size(), mcM, mcF};
    }

    /** 批量模式：对一个目录下所有 .jar 逐个判定，输出可直接贴进报告的表。 */
    static void batch(String dirName, String out) throws Exception {
        List<Path> jars = new ArrayList<>();
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(Paths.get(dirName), "*.jar")) {
            for (Path p : ds) jars.add(p);
        }
        jars.sort(Comparator.comparing(p -> p.getFileName().toString()));
        StringBuilder csv = new StringBuilder("mod,total,resolve,rename,sigchg,missing,external,judged,auto_fix_pct,as_is_pct\n");
        int sTot = 0, sJudged = 0, sOk = 0, sRn = 0, sSg = 0, sMs = 0;
        System.out.printf("%-34s %6s %7s %7s %7s %7s %8s %8s%n",
                "mod", "refs", "RESOLVE", "RENAME", "SIGCHG", "MISS", "auto-fix", "as-is");
        for (Path p : jars) {
            int[] r = analyze(p.toString());
            int tot = r[0], ok = r[1], rn = r[2], sg = r[3], ms = r[4], ex = r[5];
            int judged = tot - ex;
            double fix = 100.0 * (ok + rn) / Math.max(1, judged);
            double asis = 100.0 * ok / Math.max(1, judged);
            String name = p.getFileName().toString();
            if (name.length() > 33) name = name.substring(0, 30) + "...";
            System.out.printf("%-34s %6d %7d %7d %7d %7d %7.1f%% %7.1f%%%n", name, tot, ok, rn, sg, ms, fix, asis);
            csv.append(p.getFileName()).append(',').append(tot).append(',').append(ok).append(',')
               .append(rn).append(',').append(sg).append(',').append(ms).append(',').append(ex).append(',')
               .append(judged).append(',').append(String.format("%.1f", fix)).append(',')
               .append(String.format("%.1f", asis)).append('\n');
            sTot += tot; sJudged += judged; sOk += ok; sRn += rn; sSg += sg; sMs += ms;
        }
        System.out.printf("%-34s %6d %7d %7d %7d %7d %7.1f%% %7.1f%%%n", "TOTAL (" + jars.size() + " mods)",
                sTot, sOk, sRn, sSg, sMs,
                100.0 * (sOk + sRn) / Math.max(1, sJudged), 100.0 * sOk / Math.max(1, sJudged));
        System.out.printf("=> aggregate: %d refs judged, %d need manual work (SIGCHG %d + MISSING %d)%n",
                sJudged, sSg + sMs, sSg, sMs);
        if (out != null) { Files.writeString(Paths.get(out), csv.toString()); System.err.println("[linkcheck] csv -> " + out); }
        System.exit(0);
    }

}
