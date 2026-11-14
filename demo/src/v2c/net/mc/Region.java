package net.mc;
/** 目标版本：getBlock 纯改名成 readBlock(同描述符 RENAME)；
 *  getBiome 连签名都变了(SIGCHG) 需宿主桥。classify 带分支 -> StackMapTable,
 *  检验默认改写宿主时字节仍合法(不 VerifyError)。 */
public class Region {
    public int readBlock(int x, int y, int z) { return 42; }
    public int getBiomeAt(BlockPos p) { return p.x + p.y + p.z; }
    public int classify(int x) { if (x > 0) return 1; else return -1; }
    public static String version() { return "1.21.1-COMBO"; }
}
