package mcport;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;

/**
 * CallKind —— 从 mod jar 的字节码里恢复每条 Methodref 的调用形态。
 *
 * LinkCheck 的工单只保留 owner.name+desc (JVMS §5.4.3 的链接三元组)，
 * 丢掉了 invoke 指令；而 HostBridge 的 6 列规则必须区分 virtual / static，
 * 否则注入的方法访问标志与 adapter 描述符都会错。猜 static 会让
 * invokevirtual 在解析期抛 IncompatibleClassChangeError。
 *
 * 输出 TSV: owner \t name \t desc \t kind
 *   kind = static | virtual | interface | special | mixed | other
 * 同一三元组出现多种 opcode 一律记为 mixed；bridgegen 必须 fail-loud 拒绝。
 * INVOKEINTERFACE / INVOKESPECIAL 也不生成可执行规则（接口 default method、
 * private/super 调用语义不同），只作为可审计的分类输出。
 */
public final class CallKind {
    public static void main(String[] a) throws Exception {
        if (a.length < 4) {
            System.err.println("usage: CallKind --in <jar> [--in <jar> ...] --out <tsv>");
            System.exit(2);
        }
        List<String> jars = new ArrayList<>();
        String out = null;
        for (int i = 0; i < a.length; i++) {
            if (a[i].equals("--in")) {
                if (++i >= a.length) throw new IllegalArgumentException("missing --in value");
                jars.add(a[i]);
            } else if (a[i].equals("--out")) {
                if (++i >= a.length) throw new IllegalArgumentException("missing --out value");
                out = a[i];
            }
            else throw new IllegalArgumentException("unknown arg: " + a[i]);
        }
        if (out == null || jars.isEmpty()) throw new IllegalArgumentException("missing --in/--out");
        Map<String, Set<String>> kinds = new TreeMap<>();
        for (String j : jars) scan(j, kinds);
        List<String> lines = new ArrayList<>();
        for (Map.Entry<String, Set<String>> e : kinds.entrySet()) {
            String k = e.getValue().size() == 1 ? e.getValue().iterator().next() : "mixed";
            lines.add(e.getKey() + "\t" + k);
        }
        Files.write(Paths.get(out), lines);
        System.err.println("[callkind] jars=" + jars.size() + " refs=" + lines.size());
    }

    private static void scan(String jar, Map<String, Set<String>> kinds) throws IOException {
        try (ZipInputStream zin = new ZipInputStream(new FileInputStream(jar))) {
            ZipEntry e;
            while ((e = zin.getNextEntry()) != null) {
                if (!e.getName().endsWith(".class")) continue;
                byte[] d = zin.readAllBytes();
                new ClassReader(d).accept(new ClassVisitor(Opcodes.ASM9) {
                    @Override public MethodVisitor visitMethod(int acc, String n, String d, String s, String[] ex) {
                        return new MethodVisitor(Opcodes.ASM9) {
                            @Override public void visitMethodInsn(int op, String o, String n2, String d2, boolean itf) {
                                String k;
                                switch (op) {
                                    case Opcodes.INVOKESTATIC:    k = "static"; break;
                                    case Opcodes.INVOKEVIRTUAL:   k = "virtual"; break;
                                    case Opcodes.INVOKEINTERFACE: k = "interface"; break;
                                    case Opcodes.INVOKESPECIAL:   k = "special"; break;
                                    default:                      k = "other";
                                }
                                kinds.computeIfAbsent(o + "\t" + n2 + "\t" + d2,
                                        x -> new TreeSet<>()).add(k);
                            }
                        };
                    }
                }, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
            }
        }
    }
}
