package demo;
import net.mc.World;
public class GateMod {
    public static void main(String[] args) {
        World w = new World();
        System.out.println("gatemod block=" + w.getBlock(1, 2, 3));
    }
}
