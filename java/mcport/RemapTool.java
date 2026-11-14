package mcport;

import org.objectweb.asm.*;
import org.objectweb.asm.commons.*;
import org.objectweb.asm.tree.*;
import java.io.*;
import java.util.zip.*;

/**
 * McPort RemapTool: 离线（构建期 / dry-run）字节码重映射。
 * 全部映射逻辑在 Mapping 里，与启动期 McPortRuntime 共用同一实现。
 *
 * 用法: java -cp "build:lib/*" mcport.RemapTool --map map.tsv --in in.jar --out out.jar
 * 映射表格式见 Mapping 的 javadoc；支持可选的 S 行做继承成员解析。
 *
 * 注意: 方法/字段的**声明名**(ClassRemapper.visitMethod)不会被改，只改引用，
 * 因此不会破坏 override。这个限制对 Mixin 的 @Shadow 声明是个硬缺口，见 REPORT §8。
 */
public class RemapTool {
    static final Mapping MAP = new Mapping();
    static final MixinRewriter MIXIN = new MixinRewriter(MAP);

    public static void main(String[] a) throws Exception {
        String map = null, in = null, out = null;
        for (int i = 0; i < a.length; i++) {
            switch (a[i]) {
                case "--map": map = a[++i]; break;
                case "--in": in = a[++i]; break;
                case "--out": out = a[++i]; break;
                default: System.err.println("unknown arg: " + a[i]); System.exit(2);
            }
        }
        if (map == null || in == null || out == null) {
            System.err.println("usage: RemapTool --map map.tsv --in in.jar --out out.jar");
            System.exit(2);
        }
        MAP.load(map);
        System.err.printf("[mcport] loaded %s%n", MAP.summary());
        try (ZipInputStream zin = new ZipInputStream(new FileInputStream(in));
             ZipOutputStream zout = new ZipOutputStream(new FileOutputStream(out))) {
            ZipEntry e;
            while ((e = zin.getNextEntry()) != null) {
                byte[] data = zin.readAllBytes();
                String name = e.getName();
                if (name.endsWith(".class") && !name.startsWith("META-INF/versions/")) {
                    ClassReader cr = new ClassReader(data);
                    ClassNode node = new ClassNode();
                    cr.accept(node, ClassReader.EXPAND_FRAMES);
                    MIXIN.rewrite(node);                       // ① 注解字符串（intermediary 命名空间）
                    ClassWriter cw = new ClassWriter(0);
                    node.accept(new ClassRemapper(cw, MAP.remapper()));   // ② 常量池/描述符
                    data = cw.toByteArray();
                }
                zout.putNextEntry(new ZipEntry(name));
                zout.write(data);
                zout.closeEntry();
            }
        }
        System.err.printf("[mcport] wrote %s (inherited-member fixes: %s; mixin-strings changed=%d unresolved=%d)%n",
                out, MAP.inherited(), MIXIN.changed, MIXIN.unresolved);
    }
}
