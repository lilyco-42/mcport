package mcport;

import org.objectweb.asm.*;
import java.io.*;
import java.util.*;
import java.util.zip.*;

/** 诊断工具：列出 mod 字节码里所有含 intermediary token 的注解字符串值。 */
public class AnnotationDump {
    static final List<String> SAMPLES = new ArrayList<>();
    static final Map<String,Integer> BYDESC = new TreeMap<>();

    static class AV extends AnnotationVisitor {
        AV(AnnotationVisitor av) { super(Opcodes.ASM9, av); }
        @Override public void visit(String name, Object value) {
            if (value instanceof String && isInter((String) value)) record(name, (String) value);
            super.visit(name, value);
        }
        @Override public AnnotationVisitor visitArray(String name) {
            return new AV(super.visitArray(name));
        }
        @Override public AnnotationVisitor visitAnnotation(String name, String descriptor) {
            return new AV(super.visitAnnotation(name, descriptor));
        }
    }
    static boolean isInter(String s) {
        return s.contains("class_") || s.contains("method_") || s.contains("field_");
    }
    static synchronized void record(String name, String v) {
        BYDESC.merge(name == null ? "<array>" : name, 1, Integer::sum);
        if (SAMPLES.size() < 60) SAMPLES.add((name == null ? "<array>" : name) + " = " + v);
    }
    static class CV extends ClassVisitor {
        CV() { super(Opcodes.ASM9); }
        @Override public AnnotationVisitor visitAnnotation(String d, boolean v) {
            BYDESC.merge("class:"+d, 1, Integer::sum); return new AV(null);
        }
        @Override public FieldVisitor visitField(int a, String n, String d, String s, Object v) {
            return new FieldVisitor(Opcodes.ASM9) {
                @Override public AnnotationVisitor visitAnnotation(String d, boolean b) { return new AV(null); }
                @Override public AnnotationVisitor visitTypeAnnotation(int t, TypePath p, String d, boolean b) { return new AV(null); }
            };
        }
        @Override public MethodVisitor visitMethod(int a, String n, String d, String s, String[] e) {
            return new MethodVisitor(Opcodes.ASM9) {
                @Override public AnnotationVisitor visitAnnotation(String d, boolean b) {
                    BYDESC.merge("method:"+d, 1, Integer::sum); return new AV(null);
                }
                @Override public AnnotationVisitor visitParameterAnnotation(int p, String d, boolean b) { return new AV(null); }
                @Override public AnnotationVisitor visitAnnotationDefault() { return new AV(null); }
                @Override public AnnotationVisitor visitTypeAnnotation(int t, TypePath p, String d, boolean b) { return new AV(null); }
                @Override public AnnotationVisitor visitInsnAnnotation(int t, TypePath p, String d, boolean b) { return new AV(null); }
                @Override public AnnotationVisitor visitLocalVariableAnnotation(int t, TypePath p, Label[] st, Label[] en, int[] ix, String d, boolean b) { return new AV(null); }
            };
        }
    }
    public static void main(String[] a) throws Exception {
        for (String jar : a) {
            try (ZipInputStream z = new ZipInputStream(new FileInputStream(jar))) {
                ZipEntry e;
                while ((e = z.getNextEntry()) != null) {
                    if (e.getName().endsWith(".class")) new ClassReader(z.readAllBytes()).accept(new CV(), ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
                }
            }
        }
        System.out.println("=== annotation value keys (top 30) ===");
        BYDESC.entrySet().stream().sorted((x,y)->y.getValue()-x.getValue()).limit(30)
               .forEach(x->System.out.println("  "+x.getValue()+"\t"+x.getKey()));
        System.out.println("=== samples ===");
        SAMPLES.forEach(s->System.out.println("  "+s));
    }
}
