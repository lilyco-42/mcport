package demo;
import net.mc.Region;
import java.lang.reflect.Method;
import java.util.*;
/** 同一 mod 同时含 RENAME 引用(getBlock) 与 SIGCHG 引用(getBiome)。 */
public final class ComboMod {
    public static void main(String[] a) {
        Region r = new Region();
        System.out.println("combo on " + Region.version()
                + " block=" + r.getBlock(1,2,3) + " biome=" + r.getBiome(1,2,3));
        List<String> ms = new ArrayList<>();
        for (Method m : Region.class.getDeclaredMethods())
            ms.add(m.getName()+"/"+m.getParameterCount());
        Collections.sort(ms);
        System.out.println("region methods=" + ms);
    }
}
