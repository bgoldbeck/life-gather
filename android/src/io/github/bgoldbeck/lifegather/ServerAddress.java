package io.github.bgoldbeck.lifegather;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/** Turns what the user typed into a server origin such as http://192.168.1.20:8787. */
final class ServerAddress {
    private ServerAddress() {}

    /** Returns scheme://host[:port], or null when the text is not a usable address. */
    static String normalize(String typed) {
        if (typed == null) return null;
        String text = typed.trim();
        if (text.isEmpty() || text.contains(" ")) return null;
        if (!text.contains("://")) text = "http://" + text;
        URI uri;
        try {
            uri = new URI(text);
        } catch (URISyntaxException e) {
            return null;
        }
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
        String host = uri.getHost();
        if (!scheme.equals("http") && !scheme.equals("https")) return null;
        if (host == null || host.isEmpty() || uri.getRawUserInfo() != null) return null;
        int port = uri.getPort();
        StringBuilder origin = new StringBuilder(scheme).append("://").append(host.toLowerCase(Locale.ROOT));
        if (port != -1) {
            if (port < 1 || port > 65535) return null;
            boolean defaultPort = (scheme.equals("http") && port == 80) || (scheme.equals("https") && port == 443);
            if (!defaultPort) origin.append(':').append(port);
        }
        return origin.toString();
    }

    /** True when url is on exactly this origin (same scheme, host and port). */
    static boolean sameOrigin(String origin, String url) {
        if (origin == null || url == null) return false;
        String other;
        try {
            URI uri = new URI(url);
            if (uri.getHost() == null || uri.getRawUserInfo() != null) return false;
            other = normalize(uri.getScheme() + "://" + uri.getRawAuthority());
        } catch (URISyntaxException e) {
            return false;
        }
        return origin.equals(other);
    }
}
