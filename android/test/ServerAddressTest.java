package io.github.bgoldbeck.lifegather;

/** Plain-JVM checks for ServerAddress, run by build.sh before packaging. */
public final class ServerAddressTest {
    private static int failures;

    private static void same(String expected, String actual) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            failures++;
            System.err.println("expected " + expected + " but got " + actual);
        }
    }

    private static void yes(boolean value, String what) {
        if (!value) {
            failures++;
            System.err.println("expected true: " + what);
        }
    }

    public static void main(String[] args) {
        same("http://192.168.1.20:8787", ServerAddress.normalize("192.168.1.20:8787"));
        same("http://192.168.1.20:8787", ServerAddress.normalize("  http://192.168.1.20:8787/  "));
        same("http://192.168.1.20:8787", ServerAddress.normalize("HTTP://192.168.1.20:8787/photos?x=1#y"));
        same("http://nas.local:8787", ServerAddress.normalize("http://NAS.local:8787"));
        same("http://192.168.1.20", ServerAddress.normalize("http://192.168.1.20:80"));
        same("https://lifegather.example", ServerAddress.normalize("https://lifegather.example:443/"));
        same(null, ServerAddress.normalize(""));
        same(null, ServerAddress.normalize("http://"));
        same(null, ServerAddress.normalize("ftp://192.168.1.20"));
        same(null, ServerAddress.normalize("http://user:pw@192.168.1.20:8787"));
        same(null, ServerAddress.normalize("192.168.1.20 8787"));
        same(null, ServerAddress.normalize("javascript:alert(1)"));
        yes(ServerAddress.sameOrigin("http://192.168.1.20:8787", "http://192.168.1.20:8787/?share=empty"), "same origin");
        yes(!ServerAddress.sameOrigin("http://192.168.1.20:8787", "http://192.168.1.20:8788/"), "other port");
        yes(!ServerAddress.sameOrigin("http://192.168.1.20:8787", "https://192.168.1.20:8787/"), "other scheme");
        yes(!ServerAddress.sameOrigin("http://192.168.1.20:8787", "https://accounts.google.com/o/oauth2"), "other host");
        yes(!ServerAddress.sameOrigin("http://192.168.1.20:8787", "http://evil@192.168.1.20:8787/"), "user info");
        yes(!ServerAddress.sameOrigin(null, "http://192.168.1.20:8787/"), "no server yet");
        if (failures > 0) {
            System.err.println(failures + " ServerAddress check(s) failed");
            System.exit(1);
        }
        System.out.println("ServerAddress checks passed");
    }
}
