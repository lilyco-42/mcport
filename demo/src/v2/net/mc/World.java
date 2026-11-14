package net.mc;
/** 模拟 1.21.x 的游戏 API: getBlock -> getBlockState, 且新增了一个重载。 */
public class World {
    public int getBlockState(int x, int y, int z) { return 42; }
    public int getBlockState(BlockPos p) { return 42; }
    public static String version() { return "1.21.1"; }
}
