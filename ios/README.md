# LifeGather iPhone app

A small `WKWebView` wrapper for self-hosted LifeGather on the home network, the
iPhone counterpart of [`android/`](../android). What it does and the user's
steps to build and install it: [docs/IPHONE_APP.md](../docs/IPHONE_APP.md).

## Building

Open `LifeGather.xcodeproj` in Xcode on a Mac, choose a Team for both targets
(Signing & Capabilities, automatic signing) and Run or Archive. A paid Apple
Developer Program team is needed: the app and its Share extension exchange
files through an App Group, which personal teams can't use.

`Config/LifeGather.xcconfig` holds what is shared by both targets: the bundle ID
(`LIFEGATHER_BUNDLE_ID`; the extension is `.share`, the App Group
`group.<bundle ID>`), the version and the deployment target (iOS 15). There are
no third-party dependencies, packages or build scripts.

The project file was written by hand, not by Xcode. When adding a source file,
add it in Xcode (which updates `project.pbxproj`) and tick the target(s) that
compile it: `Shared/` files used by the extension belong to both targets.

## Checks without a Mac

```sh
ios/check.sh
```

Compiles `Shared/` with `Tests/main.swift` using any Swift toolchain (Xcode's,
or swift.org's on Linux) and runs the address and share-folder checks, which
mirror `android/test/ServerAddressTest.java`. It also checks that
`MARKETING_VERSION` matches `backend/src/lifegather/version.py`. The UIKit,
WebKit and Network code only compiles with Xcode.

## Versions

`MARKETING_VERSION` follows LifeGather's version. TestFlight needs a higher
`CURRENT_PROJECT_VERSION` for each upload of the same version; let Xcode's
upload step manage it, or raise it in the xcconfig.

## Files

- `LifeGather/AppDelegate.swift`: window, home-screen quick action, foreground/background
- `LifeGather/MainViewController.swift`: server-address screen, web view, links, dialogs, share bridge
- `LifeGather/LoopbackRelay.swift`: relays `127.0.0.1:8787` on the iPhone to the home server
- `LifeGatherShare/ShareViewController.swift`: the Share extension
- `Shared/ServerAddress.swift`: address parsing and checks
- `Shared/ShareInbox.swift`: the App Group folder that holds shared files until the page claims them
- `Tests/main.swift`, `check.sh`: checks that run without a Mac
