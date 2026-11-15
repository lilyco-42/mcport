package demo;
/** Long/Double 双槽常量 + modified UTF-8 的 NUL 常量，验证 cp 解析器不会跳错槽。 */
public class WideCp {
    public static long wide() {
        long l = 123456789012345L;
        double d = 2.5;
        String s = "a\000b" + new String(Character.toChars(0x1F600));
        return l + (long) d + s.length();
    }
}
