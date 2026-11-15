package mcport;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.zip.*;

/**
 * LinkGate —— 启动期能力闸门 (REPORT §19).
 *
 * §18 的静态出货闸门发生在打包前（CI / 作者侧）；这里补上真正把 mod 装进某版本
 * 游戏前的最后一道闸门：不改动 mod 任何字节，扫描其 class 常量池，对照该 mod→该
 * 目标版本的 contract，判定它会不会在链接期崩（MISSING / SIGCHG）。
 *
 * 寄生方式：纯 JDK 手动解析 class 文件常量池，不依赖 ASM、不依赖真实客户端 jar、
 * 不需要任何 R2 / 凭据。class 文件格式是 JVM 规范契约的一部分，解析它就寄生在
 * JVM 可读契约上（JVMS §4.4）。
 *
 * 失败语义（Round 7 实测）：HotSpot 会静默吞掉 transform 里抛出的异常，所以本闸门
 * 【绝不在 transform 里抛异常】。它在 premain 阶段用 System.exit(非零) 干净拒绝；
 * 不改一个字节也能拒绝启动。premain 抛异常则 HotSpot 会 native abort（rc=134），
 * 因此本类把读表/读 jar 的异常也 catch 后转成同样的干净拒绝。
 *
 * contract 格式（每行 ≥4 列空白分隔，# 开头或空行忽略）：
 *   owner  name  desc  status
 *   status ∈ RESOLVE | RENAME | SIGCHG | MISSING（大小写不敏感）
 *
 * 判定：contract 是某 mod→某版本的唯一权威。mod jar 常量池里出现的成员引用若：
 *   - status ∈ {MISSING, SIGCHG} → 硬阻断（链接期必崩；SIGCHG 需人工 HostBridge
 *     显式 opt-in，默认不算自动可修）；
 *   - status == RENAME → McPortRuntime 可机械重命名修复，仅计数提示；
 *   - status == RESOLVE 或不在 contract → 通过（未知不赌，闸门只拦显式已知坏）。
 *
 * 参数：
 *   -Dmcport.gate=<contract.tsv>      必填（也可用 -javaagent:agent.jar=<path>）
 *   -Dmcport.gate.modjar=<mod.jar>    必填（要扫描的 mod；缺省 = 拒绝）
 *   -Dmcport.gate.policy=reject|warn  默认 reject（未知值一律 fail-closed 按 reject）
 *   参数缺失 / 读表 / 读 jar 失败一律 System.exit(2)，policy=warn 也不豁免；
 *   warn 只豁免「已成功扫描后发现的已知 blocker」。
 */
public final class LinkGate {
    private static final Set<String> BLOCK = Set.of("MISSING", "SIGCHG");
    private enum Policy { REJECT, WARN }

    public static void premain(String agentArgs, java.lang.instrument.Instrumentation inst) {
        String contractPath = System.getProperty("mcport.gate", agentArgs == null ? "" : agentArgs);
        String modJar = System.getProperty("mcport.gate.modjar", "");
        Policy policy = "warn".equalsIgnoreCase(System.getProperty("mcport.gate.policy", "reject"))
                ? Policy.WARN : Policy.REJECT;
        System.err.println("[linkgate] policy=" + policy
                + " contract=" + (contractPath.isEmpty() ? "<none>" : contractPath)
                + " modjar=" + (modJar.isEmpty() ? "<none>" : modJar));
        if (contractPath.isBlank() || modJar.isBlank()) {
            System.err.println("[linkgate] FAIL: -Dmcport.gate and -Dmcport.gate.modjar are both required");
            System.exit(2); // config error is never waived by policy=warn
            return;
        }
        try {
            Map<String, String> contract = loadContract(contractPath);
            RefSet refs = scan(modJar);
            int blockers = 0, renames = 0, resolve = 0;
            List<String> bad = new ArrayList<>();
            for (String key : refs.memberRefs) {
                String st = contract.getOrDefault(key, "RESOLVE");
                if (BLOCK.contains(st)) { blockers++; bad.add(key + " -> " + st); }
                else if ("RENAME".equals(st)) renames++;
                else resolve++;
            }
            System.err.println("[linkgate] scanned " + refs.classCount + " classes; memberRefs="
                    + refs.memberRefs.size() + " resolve=" + resolve + " rename=" + renames
                    + " blockers=" + blockers);
            for (String b : bad) System.err.println("[linkgate] BLOCKER: " + b);
            if (blockers > 0 && policy == Policy.REJECT) {
                System.err.println("[linkgate] REJECT: " + blockers
                        + " unresolvable reference(s); refusing to start (would NoSuchMethodError at link time)");
                System.exit(2);
            }
            if (blockers > 0) System.err.println("[linkgate] WARN: " + blockers
                    + " unresolved reference(s) will likely crash at runtime");
            System.err.println("[linkgate] PASS");
        } catch (Throwable t) {
            System.err.println("[linkgate] FAIL: " + t);
            System.exit(2); // unreadable input is never waived by policy=warn
        }
    }

    private static Map<String, String> loadContract(String path) throws IOException {
        Map<String, String> m = new HashMap<>();
        try (BufferedReader r = new BufferedReader(new FileReader(path, StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty() || line.startsWith("#")) continue;
                String[] p = line.split("\\s+");
                if (p.length < 4) continue;
                m.put(p[0] + "|" + p[1] + "|" + p[2], p[3].toUpperCase(Locale.ROOT));
            }
        }
        return m;
    }

    private static final class RefSet {
        int classCount = 0;
        final Set<String> memberRefs = new TreeSet<>();
    }

    private static RefSet scan(String jarPath) throws IOException {
        RefSet rs = new RefSet();
        try (ZipInputStream z = new ZipInputStream(new FileInputStream(jarPath))) {
            ZipEntry e;
            while ((e = z.getNextEntry()) != null) {
                if (e.isDirectory() || !e.getName().endsWith(".class")) continue;
                ByteArrayOutputStream bos = new ByteArrayOutputStream();
                byte[] buf = new byte[8192];
                int n;
                while ((n = z.read(buf)) > 0) bos.write(buf, 0, n);
                rs.classCount++;
                parseClass(bos.toByteArray(), rs);
            }
        }
        return rs;
    }

    /** 两遍解析 cp：Class/NameAndType 允许前向引用 Utf8，必须全部读完再解析 memberRef。 */
    private static void parseClass(byte[] b, RefSet rs) throws IOException {
        DataInputStream in = new DataInputStream(new ByteArrayInputStream(b));
        if (in.readInt() != 0xCAFEBABE) throw new IOException("bad magic");
        in.readUnsignedShort(); // minor
        in.readUnsignedShort(); // major
        int count = in.readUnsignedShort();
        int[] tag = new int[count];
        String[] utf8 = new String[count];
        int[] classIdx = new int[count];
        int[] nameIdx = new int[count];
        int[] descIdx = new int[count];
        int[] refOwner = new int[count];
        int[] refNat = new int[count];
        for (int i = 1; i < count; i++) {
            int t = in.readUnsignedByte();
            tag[i] = t;
            switch (t) {
                case 1: {
                    int len = in.readUnsignedShort();
                    byte[] bb = new byte[len];
                    in.readFully(bb);
                    utf8[i] = decodeModifiedUtf8(bb);
                    break;
                }
                case 3: case 4: in.readInt(); break;
                case 5: case 6: in.readLong(); i++; break; // long/double 占两个 cp 槽
                case 7: classIdx[i] = in.readUnsignedShort(); break;
                case 8: in.readUnsignedShort(); break;
                case 9: case 10: case 11:
                    refOwner[i] = in.readUnsignedShort();
                    refNat[i] = in.readUnsignedShort();
                    break;
                case 12:
                    nameIdx[i] = in.readUnsignedShort();
                    descIdx[i] = in.readUnsignedShort();
                    break;
                case 15: in.readUnsignedByte(); in.readUnsignedShort(); break;
                case 16: in.readUnsignedShort(); break;
                case 17: case 18: in.readUnsignedShort(); in.readUnsignedShort(); break;
                case 19: case 20: in.readUnsignedShort(); break;
                default: throw new IOException("unknown cp tag " + t + " at index " + i);
            }
        }
        for (int i = 1; i < count; i++) {
            if (tag[i] < 9 || tag[i] > 11) continue;
            int ci = refOwner[i], ni = refNat[i];
            if (ci <= 0 || ci >= count || ni <= 0 || ni >= count) continue;
            int cu = classIdx[ci], nu = nameIdx[ni], du = descIdx[ni];
            if (cu <= 0 || cu >= count || nu <= 0 || nu >= count || du <= 0 || du >= count) continue;
            String owner = utf8[cu], name = utf8[nu], desc = utf8[du];
            if (owner != null && name != null && desc != null)
                rs.memberRefs.add(owner + "|" + name + "|" + desc);
        }
    }

    /** class 文件的 CONSTANT_Utf8 是 modified UTF-8；借 DataInputStream.readUTF 精确解码。 */
    private static String decodeModifiedUtf8(byte[] bb) throws IOException {
        ByteArrayOutputStream p = new ByteArrayOutputStream();
        DataOutputStream d = new DataOutputStream(p);
        d.writeShort(bb.length);
        d.write(bb);
        return new DataInputStream(new ByteArrayInputStream(p.toByteArray())).readUTF();
    }
}
