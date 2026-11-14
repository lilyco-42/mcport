package demo;

import net.mc.World;
import net.mc.BlockPos;

/**
 * 宿主侧桥的"语义适配体"：普通人写的普通 Java，可编译、可测试、可 review。
 * HostBridge 只生成转发壳，真正"旧参数如何变成新调用"由这里决定。
 *
 * 注意：getBlock(1,2,3) 在源版本是 42，这里转发到 getBlockState(new BlockPos(...))
 * 得到 1+2+3=6 —— 不是 bug，是故意展示语义必须人工确认：
 * 机械重命名字节码永远看不到这层差异。
 */
public final class BlockAdapter {
    /** 旧 getBlock(III)I 的桥实现；首个参数是宿主 this（virtual 规则自动补）。 */
    public static int getBlock(World w, int x, int y, int z) {
        return w.getBlockState(new BlockPos(x, y, z));
    }
}
