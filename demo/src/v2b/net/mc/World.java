package net.mc;
/**
 * 模拟"改名 + 改签名"的目标版本：getBlock(III)I 彻底消失，
 * 只剩 getBlockState(BlockPos)I。这正是 LinkCheck 工单里的 SIGCHG。
 *
 * 而且行为也变了：源版本 getBlock 固定返回 42，这里返回 x+y+z。
 * 用来证明"名字+描述符对上了，语义仍可能不对"（§1 第 3 层）。
 */
public class World {
    public int getBlockState(BlockPos p) { return p.x + p.y + p.z; }
    public static String version() { return "1.21.1-SIGCHG"; }
}
