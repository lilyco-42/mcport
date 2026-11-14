package mcport;
import org.objectweb.asm.*;
import java.io.*;
import java.util.*;
import java.util.zip.*;
import java.security.MessageDigest;

/** BodyHash: 混淆名无关的方法体骨架哈希 (REPORT §13).
 *
 *  输入: 自备的 Minecraft client jar。输出 tsv 是【测量中间产物】，含
 *  (混淆/真实) 成员名与三列指纹，不得随仓库或发布包分发；
 *  tools/drift_align.py 只把它的聚合计数与匿名身份哈希写进 data/。
 *
 *  只保留 opcode 序列 + 数值/字符串常量 + 操作数索引/维度/IINC 增量，
 *  刻意抹掉所有 owner/name/desc/Type (REF) 与跳转 Label，使两版混淆短名
 *  不同也能比较。抹掉 Label 与调用目标，正是"即使骨架一致也不能证明
 *  语义一致"的证据来源：控制流目标变了、被调用方法换了，骨架都可能不变。
 *
 *  usage: java -Xmx1g -cp 'build:lib/*' mcport.BodyHash <client.jar> <out.tsv>
 */
public class BodyHash {
  static final class MV extends MethodVisitor {
    final ByteArrayOutputStream buf = new ByteArrayOutputStream();
    final DataOutputStream out = new DataOutputStream(buf);
    final ByteArrayOutputStream opbuf = new ByteArrayOutputStream();
    final DataOutputStream ops = new DataOutputStream(opbuf);
    final ByteArrayOutputStream callbuf = new ByteArrayOutputStream();
    final DataOutputStream calls = new DataOutputStream(callbuf);
    int n = 0;
    MV() { super(Opcodes.ASM9); }
    void op(int o) { n++; try { out.writeByte(o & 0xff); ops.writeByte(o & 0xff); } catch (IOException e) {} }
    void i(int x) { try { out.writeInt(x); } catch (IOException e) {} }
    void s(String v) { try { out.writeUTF(v); } catch (IOException e) {} }
    void c(String v) { try { calls.writeUTF(v); } catch (IOException e) {} }
    @Override public void visitInsn(int o) { op(o); }
    @Override public void visitIntInsn(int o, int x) { op(o); i(x); }
    @Override public void visitVarInsn(int o, int v) { op(o); i(v); }
    @Override public void visitTypeInsn(int o, String t) { op(o); c("T:" + t); }
    @Override public void visitFieldInsn(int o, String a, String b, String d) { op(o); c("F:" + a + "." + b + ":" + d); }
    @Override public void visitMethodInsn(int o, String a, String b, String d, boolean f) { op(o); c("M:" + a + "." + b + ":" + d); }
    @Override public void visitInvokeDynamicInsn(String a, String d, Handle h, Object... args) { op(Opcodes.INVOKEDYNAMIC); c("D:" + a + ":" + d); }
    @Override public void visitJumpInsn(int o, Label l) { op(o); }
    @Override public void visitLdcInsn(Object c) {
      op(Opcodes.LDC);
      if (c instanceof Number || c instanceof String || c instanceof Character) s(String.valueOf(c));
      else s("REF");
    }
    @Override public void visitIincInsn(int v, int inc) { op(Opcodes.IINC); i(v); i(inc); }
    @Override public void visitTableSwitchInsn(int min, int max, Label d, Label... ls) { op(Opcodes.TABLESWITCH); i(ls.length); }
    @Override public void visitLookupSwitchInsn(Label d, int[] k, Label[] ls) { op(Opcodes.LOOKUPSWITCH); i(k.length); }
    @Override public void visitMultiANewArrayInsn(String d, int dims) { op(Opcodes.MULTIANEWARRAY); i(dims); c("A:" + d + ":" + dims); }
    static String hex(byte[] h) { StringBuilder sb = new StringBuilder(); for (byte b : h) sb.append(String.format("%02x", b)); return sb.toString(); }
    String digest() throws Exception { return hex(MessageDigest.getInstance("SHA-256").digest(buf.toByteArray())); }
    String digestOps() throws Exception { return hex(MessageDigest.getInstance("SHA-256").digest(opbuf.toByteArray())); }
    String digestCalls() throws Exception { return hex(MessageDigest.getInstance("SHA-256").digest(callbuf.toByteArray())); }
  }

  public static void main(String[] args) throws Exception {
    if (args.length != 2) { System.err.println("usage: BodyHash <client.jar> <out.tsv>"); System.exit(2); }
    ZipFile z = new ZipFile(args[0]);
    PrintWriter w = new PrintWriter(new BufferedWriter(new FileWriter(args[1])));
    w.println("# owner\tname\tdesc\tsha256(skeleton)\tsha256(opcodes)\tsha256(calls)\tinsnCount");
    int classes = 0, methods = 0;
    Enumeration<? extends ZipEntry> en = z.entries();
    List<ZipEntry> es = new ArrayList<ZipEntry>();
    while (en.hasMoreElements()) es.add(en.nextElement());
    es.sort(Comparator.comparing(ZipEntry::getName));
    for (ZipEntry e : es) {
      if (e.isDirectory() || !e.getName().endsWith(".class")) continue;
      final String[] owner = new String[1];
      final List<String[]> rows = new ArrayList<>();
      try (InputStream in = z.getInputStream(e)) {
        ClassReader cr = new ClassReader(in);
        cr.accept(new ClassVisitor(Opcodes.ASM9) {
          @Override public void visit(int v, int a, String n, String sig, String sup, String[] itf) { owner[0] = n; }
          @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] ex) {
            if ((a & (Opcodes.ACC_ABSTRACT | Opcodes.ACC_NATIVE)) != 0) return null;
            return new MethodVisitor(Opcodes.ASM9) {
              MV mv = new MV();
              @Override public void visitInsn(int o) { mv.visitInsn(o); }
              @Override public void visitIntInsn(int o, int x) { mv.visitIntInsn(o, x); }
              @Override public void visitVarInsn(int o, int v) { mv.visitVarInsn(o, v); }
              @Override public void visitTypeInsn(int o, String t) { mv.visitTypeInsn(o, t); }
              @Override public void visitFieldInsn(int o, String a, String b, String c) { mv.visitFieldInsn(o, a, b, c); }
              @Override public void visitMethodInsn(int o, String a, String b, String c, boolean f) { mv.visitMethodInsn(o, a, b, c, f); }
              @Override public void visitInvokeDynamicInsn(String a, String b, Handle h, Object... ar) { mv.visitInvokeDynamicInsn(a, b, h, ar); }
              @Override public void visitJumpInsn(int o, Label l) { mv.visitJumpInsn(o, l); }
              @Override public void visitLdcInsn(Object c) { mv.visitLdcInsn(c); }
              @Override public void visitIincInsn(int v, int inc) { mv.visitIincInsn(v, inc); }
              @Override public void visitTableSwitchInsn(int mi, int ma, Label d, Label... ls) { mv.visitTableSwitchInsn(mi, ma, d, ls); }
              @Override public void visitLookupSwitchInsn(Label d, int[] k, Label[] ls) { mv.visitLookupSwitchInsn(d, k, ls); }
              @Override public void visitMultiANewArrayInsn(String d, int dims) { mv.visitMultiANewArrayInsn(d, dims); }
              @Override public void visitEnd() {
                try { rows.add(new String[]{ n, d, mv.digest(), mv.digestOps(), mv.digestCalls(), String.valueOf(mv.n) }); }
                catch (Exception ex) { throw new RuntimeException(ex); }
              }
            };
          }
        }, ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
      } catch (Throwable t) {
        System.err.println("WARN skip " + e.getName() + ": " + t);
        continue;
      }
      classes++;
      for (String[] r : rows) { w.println(owner[0] + "\t" + r[0] + "\t" + r[1] + "\t" + r[2] + "\t" + r[3] + "\t" + r[4] + "\t" + r[5]); methods++; }
    }
    w.close(); z.close();
    System.out.println("classes=" + classes + " methods=" + methods);
  }
}
