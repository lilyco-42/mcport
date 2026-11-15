package demo.ref;
// Synthetic mod: reads both fields, forcing two distinct Fieldref constants.
public final class RefMod {
    public static int touch() {
        Object a = net.minecraft.Api.BLEND;
        Object b = net.minecraft.Api.B;
        return (a == null ? 0 : 1) + (b == null ? 0 : 1);
    }
}
