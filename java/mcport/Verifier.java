package mcport;

import org.objectweb.asm.*;
import org.objectweb.asm.util.CheckClassAdapter;
import java.io.*;
import java.util.*;
import java.util.zip.*;

/** Verify structural integrity of every .class in a jar (post-remap sanity gate). */
public class Verifier {
    public static void main(String[] a) throws Exception {
        String jar = null;
        for (int i = 0; i < a.length; i++) if (a[i].equals("--jar")) jar = a[++i];
        if (jar == null) { System.err.println("usage: Verifier --jar x.jar"); System.exit(2); }
        int n = 0, bad = 0;
        try (ZipFile zf = new ZipFile(jar)) {
            Enumeration<? extends ZipEntry> en = zf.entries();
            while (en.hasMoreElements()) {
                ZipEntry e = en.nextElement();
                if (!e.getName().endsWith(".class") || e.getName().startsWith("META-INF/versions/")) continue;
                n++;
                try (InputStream in = zf.getInputStream(e)) {
                    byte[] data = in.readAllBytes();
                    new ClassReader(data).accept(new CheckClassAdapter(new ClassWriter(0), false), 0);
                } catch (Throwable t) {
                    bad++;
                    if (bad <= 10) System.out.println("BAD " + e.getName() + " : " + t);
                }
            }
        }
        System.out.println("classes=" + n + " bad=" + bad);
        System.exit(bad == 0 ? 0 : 1);
    }
}