# LifeGather Android app

A small WebView wrapper for self-hosted LifeGather on the home network. What it
does and how to install it: [docs/ANDROID_APP.md](../docs/ANDROID_APP.md).

## Building

Plain Java, no Gradle or Android Gradle plugin, so it builds offline from
Debian/Ubuntu packages instead of Google's SDK download:

```sh
sudo apt-get install openjdk-17-jdk-headless aapt dalvik-exchange zipalign \
  apksigner android-sdk-platform-23
export LIFEGATHER_ANDROID_KEYSTORE_PASSWORD='...'   # see Signing
android/build.sh                                     # -> android/build/LifeGather.apk
```

`build.sh` runs the plain-JVM `ServerAddress` checks, then packages with `aapt`,
compiles against the API 23 platform jar (minimum Android 7, target API 34),
dexes with `dx`, aligns and signs. It uses only Java 8 language features and no
lambdas, because `dx` does not desugar. Methods newer than API 23 (such as the
`WebResourceRequest` form of `shouldOverrideUrlLoading`) are declared without
`@Override` and still override at run time.

## Published APK

`release/LifeGather.apk` is the current signed build, committed so phones can
download it from GitHub. Replace it with a fresh `build/LifeGather.apk` when the
app itself changes.

## Signing

Phones only install an update over the existing app when both are signed with
the same key. `build.sh` reads `LIFEGATHER_ANDROID_KEYSTORE` (default
`~/.lifegather/android-release.jks`, alias `lifegather`) and creates it on first
use. Keep the keystore and its password out of Git. Losing it means
uninstalling the app once (only the server address and sign-in are lost) and
installing a build signed with the new key.

## Files

- `src/.../MainActivity.java`: server-address screen, WebView, camera, share hand-over
- `src/.../LoopbackRelay.java`: relays `127.0.0.1:8787` on the phone to the home server
- `src/.../SharedInbox.java`: files shared from other apps until the page claims them
- `src/.../PhotoFileProvider.java`: private file the camera app writes into
- `src/.../ServerAddress.java`, `test/ServerAddressTest.java`: address parsing and checks
