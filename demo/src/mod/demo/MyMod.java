package demo;

import net.mc.World;

/** 一个"只针对 1.20.1 编译"的 mod: 二进制里硬编码了 getBlock(int,int,int)。 */
public final class MyMod {
    public static void main(String[] args) {
        World w = new World();
        System.out.println("mod started on MC " + World.version()
                + " -> block=" + w.getBlock(1, 2, 3));
    }
}
