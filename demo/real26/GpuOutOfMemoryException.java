// Compile-time ONLY. This is our own tiny stub, NOT Mojang code and NOT shipped bytecode.
// It exists so javac can compile the demo caller against the *name* of a real 26.1 class;
// at runtime the classpath contains the real major-69 class extracted from the user-supplied
// 26.1 client jar, and out/stub is deliberately NOT on the runtime classpath.
package com.mojang.blaze3d;
public class GpuOutOfMemoryException extends RuntimeException {
    public GpuOutOfMemoryException(String s) { super(s); }
    public static String legacyMessage() { return "stub"; }
    public static String msg() { return "stub"; }
}
