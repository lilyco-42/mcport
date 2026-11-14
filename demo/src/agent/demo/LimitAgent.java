package demo;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import org.objectweb.asm.*;

/** 探针 agent：证明"类已加载后再加方法"被 HotSpot 拒绝（demo 场景 E3）。 */
public final class LimitAgent {
    public static Instrumentation inst;

    public static void premain(String a, Instrumentation i) {
        inst = i;
        // 关键：canRetransform=true，否则 retransformClasses 根本不会回调 transform。
        i.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader l, String name, Class<?> redefined,
                                    ProtectionDomain pd, byte[] buf) {
                if (!"net/mc/World".equals(name) || buf == null) return null;
                if (redefined == null) return null;   // pre-define 阶段故意不改
                // retransform 阶段：试图给已加载的类加一个方法 -> JVM 应拒绝
                ClassReader cr = new ClassReader(buf);
                ClassWriter cw = new ClassWriter(cr, ClassWriter.COMPUTE_MAXS);
                cr.accept(new ClassVisitor(Opcodes.ASM9, cw) {
                    @Override public void visitEnd() {
                        MethodVisitor mv = super.visitMethod(Opcodes.ACC_PUBLIC,
                                "getBlock", "(III)I", null, null);
                        mv.visitCode();
                        mv.visitIntInsn(Opcodes.BIPUSH, 42);
                        mv.visitInsn(Opcodes.IRETURN);
                        mv.visitMaxs(0, 0);
                        mv.visitEnd();
                        super.visitEnd();
                    }
                }, 0);
                return cw.toByteArray();
            }
        }, true);
    }
}
