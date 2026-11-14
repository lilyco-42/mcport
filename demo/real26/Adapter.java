package demo26;
import com.mojang.blaze3d.GpuOutOfMemoryException;
/** Pure-JDK adapter: no LWJGL / native dependency, so this loads without a game. */
public final class Adapter {
    public static String legacyMessage() {
        return "REAL-26.1-BRIDGE-OK:" + GpuOutOfMemoryException.class.getName();
    }
}
