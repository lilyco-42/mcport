package demo;

import java.lang.instrument.Instrumentation;

/** demo 场景 E3：类已加载后 retransform 加方法 -> UnsupportedOperationException。 */
public final class RetransformLimit {
    public static void main(String[] a) throws Exception {
        Class<?> w = Class.forName("net.mc.World");   // pre-define，探针不改
        System.out.println("loaded " + w.getName()
                + " methods=" + w.getDeclaredMethods().length);
        Instrumentation inst = LimitAgent.inst;
        try {
            inst.retransformClasses(w);
            System.out.println("UNEXPECTED: schema change accepted");
        } catch (UnsupportedOperationException e) {
            System.out.println("EXPECTED (HotSpot): " + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
        }
    }
}
