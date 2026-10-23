import Foundation

// Checks for the parts of the iPhone app that need no iPhone: run by
// ios/check.sh with any Swift toolchain (macOS or Linux).

var failures = 0

func same<T: Equatable>(_ expected: T, _ actual: T, _ what: String = "", line: Int = #line) {
    if expected != actual {
        failures += 1
        print("line \(line): expected \(expected) but got \(actual) \(what)")
    }
}

func yes(_ value: Bool, _ what: String, line: Int = #line) {
    if !value {
        failures += 1
        print("line \(line): expected true: \(what)")
    }
}

// ----- ServerAddress: same cases as android/test/ServerAddressTest.java -----

same("http://192.168.1.20:8787", ServerAddress.normalize("192.168.1.20:8787"))
same("http://192.168.1.20:8787", ServerAddress.normalize("  http://192.168.1.20:8787/  "))
same("http://192.168.1.20:8787", ServerAddress.normalize("HTTP://192.168.1.20:8787/photos?x=1#y"))
same("http://nas.local:8787", ServerAddress.normalize("http://NAS.local:8787"))
same("http://192.168.1.20", ServerAddress.normalize("http://192.168.1.20:80"))
same("https://lifegather.example", ServerAddress.normalize("https://lifegather.example:443/"))
same(nil, ServerAddress.normalize(""))
same(nil, ServerAddress.normalize(nil))
same(nil, ServerAddress.normalize("http://"))
same(nil, ServerAddress.normalize("ftp://192.168.1.20"))
same(nil, ServerAddress.normalize("http://user:pw@192.168.1.20:8787"))
same(nil, ServerAddress.normalize("192.168.1.20 8787"))
same(nil, ServerAddress.normalize("javascript:alert(1)"))
same(nil, ServerAddress.normalize("http://192.168.1.20:99999"))
let home = "http://192.168.1.20:8787"
yes(ServerAddress.sameOrigin(home, URL(string: "http://192.168.1.20:8787/?share=empty")), "same origin")
yes(!ServerAddress.sameOrigin(home, URL(string: "http://192.168.1.20:8788/")), "other port")
yes(!ServerAddress.sameOrigin(home, URL(string: "https://192.168.1.20:8787/")), "other scheme")
yes(!ServerAddress.sameOrigin(home, URL(string: "https://accounts.google.com/o/oauth2")), "other host")
yes(!ServerAddress.sameOrigin(home, URL(string: "http://evil@192.168.1.20:8787/")), "user info")
yes(!ServerAddress.sameOrigin(nil, URL(string: "http://192.168.1.20:8787/")), "no server yet")
yes(ServerAddress.sameOrigin("http://127.0.0.1:8787", URL(string: "http://127.0.0.1:8787/photos")), "relay origin")
let target = ServerAddress.relayTarget(home)
same("192.168.1.20", target?.host)
same(8787, target?.port)
same(80, ServerAddress.relayTarget("http://nas.local")?.port)
yes(ServerAddress.relayTarget("https://lifegather.example") == nil, "HTTPS is opened directly")

// ----- ShareInbox -----

let scratch = URL(fileURLWithPath: NSTemporaryDirectory())
    .appendingPathComponent("lifegather-share-check-\(UUID().uuidString)", isDirectory: true)
try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)

func sample(_ name: String, bytes: Int) throws -> URL {
    let url = scratch.appendingPathComponent(name)
    try Data(repeating: 0x2a, count: bytes).write(to: url)
    return url
}

let inbox = ShareInbox(root: scratch.appendingPathComponent("Shared"))
let now = Date()
same(nil, inbox.pending(now: now), "empty inbox")

// A share appears only once committed, and is claimed exactly once.
let draft = try inbox.begin()
yes(ShareInbox.isValidId(draft.id), "random 32-hex id")
try draft.add(copying: sample("receipt.jpg", bytes: 23), name: "Synthetic receipt.jpg", type: "image/jpeg")
try draft.add(copying: sample("big.pdf", bytes: ShareInbox.maxBytes + 5000), name: "../../Manual.pdf", type: "application/pdf")
same(nil, inbox.pending(now: now), "unfinished share stays hidden")
yes(try inbox.commit(draft, now: now), "commit")
same("?share=\(draft.id)", inbox.pending(now: now.addingTimeInterval(5)))
let entries = inbox.claim(draft.id)
same([
    ShareInbox.Entry(name: "Synthetic receipt.jpg", type: "image/jpeg", size: 23),
    ShareInbox.Entry(name: "Manual.pdf", type: "application/pdf", size: ShareInbox.maxBytes + 1),
], entries ?? [], "names cleaned, large file cut one byte past the limit")
yes(inbox.claim(draft.id) == nil, "second claim gets nothing")
same(nil, inbox.pending(now: now.addingTimeInterval(5)), "claimed share is not offered again")
same(23, inbox.take(draft.id, index: 0)?.count)
same(nil, inbox.take(draft.id, index: 0)?.count, "each file is handed over once")
same(nil, inbox.take("not-an-id", index: 1)?.count)
same(ShareInbox.maxBytes + 1, inbox.take(draft.id, index: 1)?.count)
yes(!FileManager.default.fileExists(atPath: scratch.appendingPathComponent("Shared/\(draft.id)").path),
    "share folder removed once every file is taken")

// Unclaimed shares can't be read file by file.
let unclaimed = try inbox.begin()
try unclaimed.add(copying: sample("a.png", bytes: 3), name: "a.png", type: "image/png")
_ = try inbox.commit(unclaimed, now: now)
same(nil, inbox.take(unclaimed.id, index: 0)?.count, "take needs a claim first")

// Over the limit: ten files kept, the page is told there were more.
let full = try inbox.begin()
for index in 0..<12 {
    try full.add(copying: sample("p\(index).jpg", bytes: 1), name: "p\(index).jpg", type: "image/jpeg")
}
same(ShareInbox.limit, full.count)
_ = try inbox.commit(full, now: now.addingTimeInterval(30))
same("?share=\(full.id)&more=1", inbox.pending(now: now.addingTimeInterval(31)), "newest share first")

// Nothing usable: the empty share is removed instead of committed.
let empty = try inbox.begin()
yes(try !inbox.commit(empty, now: now), "empty share not committed")

// Shares expire after an hour.
same(nil, inbox.pending(now: now.addingTimeInterval(ShareInbox.lifetime + 60)), "expired")
let left = (try? FileManager.default.contentsOfDirectory(atPath: scratch.appendingPathComponent("Shared").path)) ?? []
same([String](), left, "expired shares deleted")

same("Shared file", ShareInbox.cleanName("  "))
same("x.txt", ShareInbox.cleanName("a/b\\x.txt"))

try? FileManager.default.removeItem(at: scratch)

if failures > 0 {
    print("\(failures) iPhone app check(s) failed")
    exit(1)
}
print("iPhone app checks passed")
