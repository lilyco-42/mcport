package demo26;
import com.mojang.blaze3d.GpuOutOfMemoryException;
/** Calls a method that the real 26.1 class does NOT declare. */
public class Legacy {
    public static void main(String[] a) throws Exception {
        System.out.println("msg=" + GpuOutOfMemoryException.legacyMessage());
        System.out.println("major=" + major());
        System.out.println("declared=" + methods());
    }
    static int major() throws Exception {
        try (var in = GpuOutOfMemoryException.class.getResourceAsStream(
                "GpuOutOfMemoryException.class")) {
            byte[] b = in.readAllBytes();
            return ((b[6] & 0xff) << 8) | (b[7] & 0xff);
        }
    }
    static String methods() {
        StringBuilder sb = new StringBuilder();
        for (var m : GpuOutOfMemoryException.class.getDeclaredMethods())
            sb.append(m.getName()).append(" ");
        return sb.toString().trim();
    }
}
