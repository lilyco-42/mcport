package net.mc;
/** 组合实验源版本：两个旧引用，一个将来纯改名(RENAME)，一个将来改签名(SIGCHG)。 */
public class Region {
    public int getBlock(int x, int y, int z) { return 42; }
    public int getBiome(int x, int y, int z) { return 7; }
    public static String version() { return "1.20.1-COMBO"; }
}
