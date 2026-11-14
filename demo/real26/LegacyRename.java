package demo26;
import com.mojang.blaze3d.GpuOutOfMemoryException;
/** RENAME case: Map rewrites msg() -> legacyMessage() in THIS class only. */
public class LegacyRename {
    public static void main(String[] a) {
        System.out.println("msg=" + GpuOutOfMemoryException.msg());
    }
}
