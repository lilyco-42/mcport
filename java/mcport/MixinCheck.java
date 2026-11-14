package mcport;

import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.io.*;
import java.util.*;
import java.util.zip.*;

/** 静态预言机补充维度：统计注解/ invokedynamic bsmArgs 里残留的 intermediary 字符串。 */
public class MixinCheck {
    static long totalStrings, interStrings, tokens, withMixin;
    static final List<String> SAMPLES = new ArrayList<>();

    static void scan(Object o) {
        if (o instanceof String) {
            String s = (String) o; totalStrings++;
            int n = count(s);
            if (n > 0) {
                interStrings++; tokens += n;
                if (SAMPLES.size() < 8) SAMPLES.add(s);
            }
        } else if (o instanceof List) { for (Object x : (List<?>) o) scan(x); }
        else if (o instanceof AnnotationNode) {
            AnnotationNode a = (AnnotationNode) o; if (a.values != null) for (int i = 1; i < a.values.size(); i += 2) scan(a.values.get(i));
        } else if (o instanceof Type) { /* 描述符由 LinkCheck 覆盖 */ }
    }
    static int count(String s) {
        int n = 0;
        for (String p : new String[]{"class_", "method_", "field_"}) {
            int i = 0; while ((i = s.indexOf(p, i)) >= 0) { int j = i + p.length(); if (j < s.length() && Character.isDigit(s.charAt(j))) n++; i = j; }
        }
        return n;
    }
    static void anns(List<?> l) { if (l != null) for (Object o : l) scan(o); }

    public static void main(String[] a) throws Exception {
        for (String jar : a) {
            try (ZipInputStream z = new ZipInputStream(new FileInputStream(jar))) {
                ZipEntry e;
                while ((e = z.getNextEntry()) != null) {
                    if (!e.getName().endsWith(".class")) continue;
                    ClassNode cn = new ClassNode();
                    new ClassReader(z.readAllBytes()).accept(cn, ClassReader.SKIP_CODE | ClassReader.SKIP_DEBUG | ClassReader.SKIP_FRAMES);
                    boolean mix = false;
                    if (cn.visibleAnnotations != null) for (AnnotationNode an : cn.visibleAnnotations)
                        if (an.desc != null && an.desc.contains("asm/mixin/Mixin")) mix = true;
                    if (cn.invisibleAnnotations != null) for (AnnotationNode an : cn.invisibleAnnotations)
                        if (an.desc != null && an.desc.contains("asm/mixin/Mixin")) mix = true;
                    if (mix) withMixin++;
                    anns(cn.visibleAnnotations); anns(cn.invisibleAnnotations);
                    anns(cn.visibleTypeAnnotations); anns(cn.invisibleTypeAnnotations);
                    if (cn.fields != null) for (FieldNode f : cn.fields) {
                        anns(f.visibleAnnotations); anns(f.invisibleAnnotations);
                        anns(f.visibleTypeAnnotations); anns(f.invisibleTypeAnnotations);
                    }
                    if (cn.methods != null) for (MethodNode mn : cn.methods) {
                        anns(mn.visibleAnnotations); anns(mn.invisibleAnnotations);
                        anns(mn.visibleTypeAnnotations); anns(mn.invisibleTypeAnnotations);
                        if (mn.visibleParameterAnnotations != null) for (List<AnnotationNode> l : mn.visibleParameterAnnotations) anns(l);
                        if (mn.invisibleParameterAnnotations != null) for (List<AnnotationNode> l : mn.invisibleParameterAnnotations) anns(l);
                        anns(mn.visibleLocalVariableAnnotations); anns(mn.invisibleLocalVariableAnnotations);
                        if (mn.instructions != null) for (AbstractInsnNode ins : mn.instructions)
                            if (ins instanceof InvokeDynamicInsnNode)
                                for (Object b : ((InvokeDynamicInsnNode) ins).bsmArgs) scan(b);
                    }
                }
            }
        }
        System.out.printf("mixinClasses=%d annotationStrings=%d interStrings=%d interTokens=%d%n",
                withMixin, totalStrings, interStrings, tokens);
        SAMPLES.forEach(s -> System.out.println("  sample: " + s));
    }
}
