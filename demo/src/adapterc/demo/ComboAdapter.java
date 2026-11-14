package demo;
import net.mc.Region;
import net.mc.BlockPos;
/** 语义适配：旧 getBiome(III)I -> 新 getBiomeAt(BlockPos)。源值 7 -> 6 显式暴露漂移。 */
public final class ComboAdapter {
    public static int getBiome(Region r, int x, int y, int z) {
        return r.getBiomeAt(new BlockPos(x,y,z));
    }
}
