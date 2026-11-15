package net.mc;
/** 与 gateapi 同名同签名，但行为不同：静态链接闸门 detection 不到的语义漂移。 */
public class World {
    public int getBlock(int x, int y, int z) { return x + y + z; }
}
