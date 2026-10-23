import Foundation

/// Files shared to LifeGather from another app, kept in the App Group folder
/// that the Share Extension and the app both see. Like the Android app's
/// SharedInbox, the signed-in page claims a share once and then saves each file
/// through the normal Photos or Documents upload; each file is deleted as soon
/// as the page has taken it.
///
/// Layout: <root>/<32-hex id>/{0,1,…, share.json}. share.json is written last, so
/// a share without it is unfinished. Claiming renames it to claimed.json, so the
/// app never offers the same share twice.
final class ShareInbox {
    /// Same limits as the web share target (frontend/src/shareTarget.ts, sw.js).
    static let limit = 10
    static let maxBytes = 8 * 1024 * 1024
    /// The user opens the app themselves after sharing, so a share waits a while.
    static let lifetime: TimeInterval = 60 * 60

    struct Entry: Codable, Equatable {
        let name: String
        let type: String
        let size: Int
    }

    struct Manifest: Codable {
        let created: Date
        let more: Bool
        let files: [Entry]
    }

    private let root: URL
    private let files = FileManager.default

    init(root: URL) {
        self.root = root
        try? files.createDirectory(at: root, withIntermediateDirectories: true)
    }

    #if os(iOS)
    /// The inbox in the App Group named by the LifeGatherAppGroup Info.plist key.
    static func shared() -> ShareInbox? {
        guard let group = Bundle.main.object(forInfoDictionaryKey: "LifeGatherAppGroup") as? String,
              let container = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group)
        else { return nil }
        return ShareInbox(root: container.appendingPathComponent("Shared", isDirectory: true))
    }
    #endif

    static func isValidId(_ id: String) -> Bool {
        id.count == 32 && id.allSatisfy { "0123456789abcdef".contains($0) }
    }

    // MARK: Share Extension side

    /// A share being written. Nothing is visible to the app until commit().
    final class Draft {
        let id: String
        fileprivate let dir: URL
        fileprivate var entries: [Entry] = []
        fileprivate var more = false

        fileprivate init(id: String, dir: URL) {
            self.id = id
            self.dir = dir
        }

        var count: Int { entries.count }

        /// Notes that more than `limit` files were shared, so the page can say so.
        func markMore() {
            more = true
        }

        /// Copies at most maxBytes + 1 bytes of source, so the page can still say
        /// "too large" without the whole file being kept. Returns false once the
        /// share is full.
        @discardableResult
        func add(copying source: URL, name: String, type: String) throws -> Bool {
            guard entries.count < ShareInbox.limit else {
                more = true
                return false
            }
            let target = dir.appendingPathComponent(String(entries.count))
            let input = try FileHandle(forReadingFrom: source)
            defer { try? input.close() }
            guard FileManager.default.createFile(atPath: target.path, contents: nil) else {
                throw CocoaError(.fileWriteUnknown)
            }
            let output = try FileHandle(forWritingTo: target)
            defer { try? output.close() }
            var size = 0
            while size <= ShareInbox.maxBytes {
                let chunk = input.readData(ofLength: min(256 * 1024, ShareInbox.maxBytes + 1 - size))
                if chunk.isEmpty { break }
                output.write(chunk)
                size += chunk.count
            }
            entries.append(Entry(name: ShareInbox.cleanName(name), type: type, size: size))
            return true
        }
    }

    func begin() throws -> Draft {
        let id = ShareInbox.newId()
        let dir = root.appendingPathComponent(id, isDirectory: true)
        try files.createDirectory(at: dir, withIntermediateDirectories: true)
        return Draft(id: id, dir: dir)
    }

    /// Makes the share visible to the app. Returns false (and removes it) when
    /// nothing usable was added.
    func commit(_ draft: Draft, now: Date = Date()) throws -> Bool {
        guard !draft.entries.isEmpty else {
            discard(draft)
            return false
        }
        let manifest = Manifest(created: now, more: draft.more, files: draft.entries)
        try ShareInbox.encoder.encode(manifest)
            .write(to: draft.dir.appendingPathComponent("share.json"), options: .atomic)
        return true
    }

    func discard(_ draft: Draft) {
        try? files.removeItem(at: draft.dir)
    }

    // MARK: App side

    /// The newest share waiting for the page, as the address query to open
    /// (share=<id>, plus more=1 when over the limit). Removes expired shares.
    func pending(now: Date = Date()) -> String? {
        removeExpired(now: now)
        var newest: (id: String, manifest: Manifest)?
        for id in shareIds() {
            guard let manifest = read(id, "share.json") else { continue }
            if newest == nil || manifest.created > newest!.manifest.created { newest = (id, manifest) }
        }
        guard let found = newest else { return nil }
        return "?share=\(found.id)" + (found.manifest.more ? "&more=1" : "")
    }

    /// The page's one claim of a share: its file list, or nil when the share is
    /// unknown or already claimed.
    func claim(_ id: String) -> [Entry]? {
        guard ShareInbox.isValidId(id) else { return nil }
        let dir = root.appendingPathComponent(id, isDirectory: true)
        guard let manifest = read(id, "share.json") else { return nil }
        do {
            try files.moveItem(at: dir.appendingPathComponent("share.json"),
                               to: dir.appendingPathComponent("claimed.json"))
        } catch {
            return nil
        }
        return Array(manifest.files.prefix(ShareInbox.limit))
    }

    /// One file of a claimed share, handed over once and then deleted.
    func take(_ id: String, index: Int) -> Data? {
        guard ShareInbox.isValidId(id), (0..<ShareInbox.limit).contains(index),
              read(id, "claimed.json") != nil else { return nil }
        let dir = root.appendingPathComponent(id, isDirectory: true)
        let file = dir.appendingPathComponent(String(index))
        guard let data = try? Data(contentsOf: file) else { return nil }
        try? files.removeItem(at: file)
        let left = (try? files.contentsOfDirectory(atPath: dir.path)) ?? []
        if left.allSatisfy({ $0 == "claimed.json" }) { try? files.removeItem(at: dir) }
        return data
    }

    /// Unfinished, claimed or old shares are removed after `lifetime`.
    func removeExpired(now: Date = Date()) {
        for id in shareIds() {
            let dir = root.appendingPathComponent(id, isDirectory: true)
            let created = read(id, "share.json")?.created ?? read(id, "claimed.json")?.created
                ?? ((try? files.attributesOfItem(atPath: dir.path))?[.modificationDate] as? Date) ?? .distantPast
            if now.timeIntervalSince(created) > ShareInbox.lifetime || created > now.addingTimeInterval(60) {
                try? files.removeItem(at: dir)
            }
        }
    }

    // MARK: Helpers

    private func shareIds() -> [String] {
        ((try? files.contentsOfDirectory(atPath: root.path)) ?? []).filter(ShareInbox.isValidId)
    }

    private func read(_ id: String, _ name: String) -> Manifest? {
        let url = root.appendingPathComponent(id, isDirectory: true).appendingPathComponent(name)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? ShareInbox.decoder.decode(Manifest.self, from: data)
    }

    private static func newId() -> String {
        var generator = SystemRandomNumberGenerator()
        return (0..<16).map { _ in String(format: "%02x", UInt8.random(in: 0...255, using: &generator)) }.joined()
    }

    /// Keeps the shown name only: no folders, no control characters.
    static func cleanName(_ name: String) -> String {
        let base = name.split(whereSeparator: { $0 == "/" || $0 == "\\" }).last.map(String.init) ?? ""
        let clean = String(base.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) })
            .trimmingCharacters(in: .whitespaces)
        return clean.isEmpty ? "Shared file" : String(clean.prefix(200))
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .secondsSince1970
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .secondsSince1970
        return decoder
    }()
}
