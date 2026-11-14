package mcport;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.commons.ClassRemapper;
import org.objectweb.asm.tree.*;

/**
 * McPortRuntime —— 启动期 -javaagent 兼容层。
 *
 * 为什么必须是启动期（premain）而不是 attach：
 *   JEP 451（JDK 21 已交付）明确规定动态加载 agent 会发警告，为将来默认禁止铺路；
 *   同时它的 Non-Goal 明确写着"不阻止通过 -javaagent/-agentlib 在启动时加载"，
 *   且不对启动期加载发警告。所以寄生方案只有启动期这一条合法长期路径。
 *
 * 为什么在 transform 里改而不是改 jar：
 *   游戏文件与 mod 文件在磁盘上都保持原样（可校验 sha1），
 *   改的只是堆里的 Class 对象，因此可以随时关掉、可以按 mod 粒度开关，
 *   也不会破坏其他加载器对 jar 的完整性校验。
 *
 * 映射逻辑完全委托给 Mapping，与离线 RemapTool 同源（含 S 行继承解析）。
 *
 * 失败的语义：一律 fail-loud。
 *   映射表里没有的引用 → 原样放过 → JVM 链接期抛 NoSuchMethodError。
 *   本 agent 绝不"猜"改名，因为猜错会产生静默的错误行为（实验 D 已证）。
 */
public final class McPortRuntime {

    private static final Mapping MAP = new Mapping();
    private static final MixinRewriter MIXIN = new MixinRewriter(MAP);
    /**
     * 默认只跳过"游戏自身与 JDK"的类, 改写其余所有类(即 mod 侧)。
     * 反过来写(只改 net/minecraft/)是错的: 需要被改写的恰恰是 mod 的字节码,
     * 游戏类在目标版本上已经是正确的了。
     *
     * com/mojang/ 必须一起跳过: 26.1 完全去混淆后, 游戏类分布在
     * net/minecraft/(10208) + com/mojang/(474), 后者是 Blaze3D/OpenAL 等渲染栈,
     * 属于游戏自身而非 mod。漏掉它会让 agent 去重写游戏类。
     * 用 -Dmcport.skip= / -Dmcport.only= 可覆盖。
     */
    private static final List<String> DEFAULT_SKIP =
            List.of("net/minecraft/", "com/mojang/", "java/", "javax/",
                    "jdk/", "sun/", "com/sun/");
    private static List<String> skip = DEFAULT_SKIP;
    private static Set<String> prefixes = new LinkedHashSet<>();   // 非空 = 只改这些前缀
    private static long rewrites;

    public static void premain(String args, Instrumentation inst) {
        String mapPath = System.getProperty("mcport.map", "");
        String only = System.getProperty("mcport.only", "");
        String skipProp = System.getProperty("mcport.skip", "");
        if (!only.isBlank()) prefixes = new LinkedHashSet<>(Arrays.asList(only.split(",")));
        if (!skipProp.isBlank()) skip = Arrays.asList(skipProp.split(","));
        if (!mapPath.isBlank()) {
            try {
                MAP.load(mapPath);
            } catch (Exception e) {
                // 加载映射表失败必须让进程起不来：否则 mod 会在运行期以
                // NoSuchMethodError 的形式"莫名其妙地"崩，比启动失败难查一万倍。
                throw new IllegalStateException("[mcport] cannot load map " + mapPath, e);
            }
        }
        System.err.printf("[mcport] map loaded: %s ; rewriting prefixes=%s%n",
                MAP.summary(), prefixes.isEmpty() ? "all-except-" + skip : prefixes.toString());
        inst.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String name, Class<?> redefined,
                                    ProtectionDomain pd, byte[] buf) {
                if (name == null || buf == null || !shouldRewrite(name)) return null;
                try {
                    ClassReader cr = new ClassReader(buf);
                    ClassNode node = new ClassNode();
                    cr.accept(node, ClassReader.EXPAND_FRAMES);
                    MIXIN.rewrite(node);
                    ClassWriter cw = new ClassWriter(0);
                    node.accept(new ClassRemapper(cw, MAP.remapper()));
                    rewrites++;
                    return cw.toByteArray();
                } catch (Throwable t) {
                    System.err.println("[mcport] FAILED to rewrite " + name + ": " + t);
                    return null;   // 交给 JVM 原样加载 → 该 mod 会在链接期明确报错
                }
            }
        });
    }

    /** 只改写"mod 侧"的类，绝不动游戏自己的类（游戏类已在目标版本，不需要改）。 */
    private static boolean shouldRewrite(String internalName) {
        if (!prefixes.isEmpty()) {
            for (String p : prefixes) if (internalName.startsWith(p)) return true;
            return false;
        }
        for (String p : skip) if (internalName.startsWith(p)) return false;
        return true;
    }

    public static long rewrites() { return rewrites; }
}
