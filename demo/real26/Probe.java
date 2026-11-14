package demo26;
import com.mojang.blaze3d.GpuOutOfMemoryException;
/** Loads the real 26.1 class without starting the game. */
public class Probe {
    public static void main(String[] a) throws Exception {
        Class<?> c = Class.forName("com.mojang.blaze3d.GpuOutOfMemoryException");
        try (var in = c.getResourceAsStream("GpuOutOfMemoryException.class")) {
            byte[] b = in.readAllBytes();
            System.out.println("LOADED " + c.getName() + " major="
                    + (((b[6] & 0xff) << 8) | (b[7] & 0xff)));
        }
    }
}
