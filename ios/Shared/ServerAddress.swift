import Foundation

/// Turns what the user typed into a server origin such as http://192.168.1.20:8787.
/// Same rules as the Android app's ServerAddress.java.
enum ServerAddress {
    /// Returns scheme://host[:port], or nil when the text is not a usable address.
    static func normalize(_ typed: String?) -> String? {
        guard var text = typed?.trimmingCharacters(in: .whitespacesAndNewlines),
              !text.isEmpty, !text.contains(" ") else { return nil }
        if !text.contains("://") { text = "http://" + text }
        guard let parts = URLComponents(string: text) else { return nil }
        let scheme = (parts.scheme ?? "").lowercased()
        guard scheme == "http" || scheme == "https" else { return nil }
        guard var host = parts.host?.lowercased(), !host.isEmpty else { return nil }
        guard parts.user == nil, parts.password == nil else { return nil }
        if host.contains(":") && !host.hasPrefix("[") { host = "[\(host)]" }
        var origin = "\(scheme)://\(host)"
        if let port = parts.port {
            guard (1...65535).contains(port) else { return nil }
            let defaultPort = (scheme == "http" && port == 80) || (scheme == "https" && port == 443)
            if !defaultPort { origin += ":\(port)" }
        }
        return origin
    }

    /// True when url is on exactly this origin (same scheme, host and port).
    static func sameOrigin(_ origin: String?, _ url: URL?) -> Bool {
        guard let origin = origin, let url = url, let scheme = url.scheme, let host = url.host,
              url.user == nil, url.password == nil else { return false }
        let authority = url.port.map { "\(host):\($0)" } ?? host
        return normalize("\(scheme)://\(authority)") == origin
    }

    /// Host and port to relay to, for a plain-HTTP origin.
    static func relayTarget(_ origin: String) -> (host: String, port: UInt16)? {
        guard let parts = URLComponents(string: origin), parts.scheme == "http",
              let host = parts.host, !host.isEmpty else { return nil }
        let port = parts.port ?? 80
        guard let value = UInt16(exactly: port), value > 0 else { return nil }
        return (host.trimmingCharacters(in: CharacterSet(charactersIn: "[]")), value)
    }
}
