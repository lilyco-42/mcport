package demo26;
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.security.ProtectionDomain;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
/** Observer transformer: dumps the bytes seen AFTER earlier -javaagent transformers. */
public final class DumpAgent {
    public static void premain(String args, Instrumentation inst) {
        inst.addTransformer(new ClassFileTransformer() {
            @Override public byte[] transform(ClassLoader loader, String name,
                    Class<?> redefined, ProtectionDomain pd, byte[] buf) {
                if (buf == null || !"com/mojang/blaze3d/GpuOutOfMemoryException".equals(name))
                    return null;
                try {
                    Files.write(Paths.get(System.getProperty("mcport.dump", "dump.class")), buf);
                    int major = ((buf[6] & 0xff) << 8) | (buf[7] & 0xff);
                    StringBuilder ms = new StringBuilder();
                    new ClassReader(buf).accept(new ClassVisitor(Opcodes.ASM9) {
                        @Override public MethodVisitor visitMethod(int a, String n,
                                String d, String s, String[] e) {
                            ms.append(n).append(d).append(" "); return null;
                        }
                    }, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
                    System.err.printf("[dump] transformed bytes=%d major=%d methods=%s%n",
                            buf.length, major, ms.toString().trim());
                } catch (Throwable t) { t.printStackTrace(); }
                return null;   // observer: never modifies
            }
        });
    }
}
