#!/usr/bin/env bash
# Builds android/build/LifeGather.apk without Gradle or Google's SDK download,
# using Debian/Ubuntu packages (see android/README.md):
#   sudo apt-get install openjdk-17-jdk-headless aapt dalvik-exchange zipalign \
#     apksigner android-sdk-platform-23
# Signing key: LIFEGATHER_ANDROID_KEYSTORE (default ~/.lifegather/android-release.jks)
# with password LIFEGATHER_ANDROID_KEYSTORE_PASSWORD. A new key is made if none
# exists; keep it, because phones only accept updates signed with the same key.
set -euo pipefail
cd "$(dirname "$0")"

SDK=${ANDROID_SDK:-/usr/lib/android-sdk}
PLATFORM=$SDK/platforms/android-23/android.jar
TOOLS=$SDK/build-tools/debian
KEYSTORE=${LIFEGATHER_ANDROID_KEYSTORE:-$HOME/.lifegather/android-release.jks}
PASSWORD=${LIFEGATHER_ANDROID_KEYSTORE_PASSWORD:-}
MIN_SDK=24
TARGET_SDK=34

for tool in "$TOOLS/aapt" "$TOOLS/dx" "$TOOLS/zipalign" "$TOOLS/apksigner" javac keytool; do
  command -v "$tool" >/dev/null || { echo "Missing $tool; see android/README.md" >&2; exit 1; }
done
[ -f "$PLATFORM" ] || { echo "Missing $PLATFORM; install android-sdk-platform-23" >&2; exit 1; }

# The app's version follows LifeGather's single version source.
VERSION=$(sed -n 's/^__version__ = "\([0-9]*\.[0-9]*\.[0-9]*\)"$/\1/p' ../backend/src/lifegather/version.py)
IFS=. read -r MAJOR MINOR PATCH <<<"$VERSION"
VERSION_CODE=$((MAJOR * 1000000 + MINOR * 1000 + PATCH))

rm -rf build
mkdir -p build/gen/io/github/bgoldbeck/lifegather build/classes build/test

# Plain-JVM checks first.
javac -d build/test src/io/github/bgoldbeck/lifegather/ServerAddress.java test/ServerAddressTest.java
java -cp build/test io.github.bgoldbeck.lifegather.ServerAddressTest

cat > build/gen/io/github/bgoldbeck/lifegather/BuildInfo.java <<JAVA
package io.github.bgoldbeck.lifegather;

final class BuildInfo {
    static final String VERSION = "$VERSION";
}
JAVA

"$TOOLS/aapt" package -f -m -J build/gen -M AndroidManifest.xml -S res -I "$PLATFORM" \
  --min-sdk-version "$MIN_SDK" --target-sdk-version "$TARGET_SDK" \
  --version-code "$VERSION_CODE" --version-name "$VERSION" -F build/unsigned.apk

javac -source 8 -target 8 -Xlint:-options -encoding UTF-8 -bootclasspath "$PLATFORM" -d build/classes \
  $(find src build/gen -name '*.java')
"$TOOLS/dx" --dex --min-sdk-version="$MIN_SDK" --output=build/classes.dex build/classes
(cd build && "$TOOLS/aapt" add unsigned.apk classes.dex >/dev/null)
"$TOOLS/zipalign" -f 4 build/unsigned.apk build/aligned.apk

if [ ! -f "$KEYSTORE" ]; then
  [ -n "$PASSWORD" ] || { echo "Set LIFEGATHER_ANDROID_KEYSTORE_PASSWORD to create a signing key" >&2; exit 1; }
  echo "Creating signing key $KEYSTORE. Keep it: updates must be signed with the same key."
  mkdir -p "$(dirname "$KEYSTORE")"
  keytool -genkeypair -keystore "$KEYSTORE" -storepass "$PASSWORD" -keypass "$PASSWORD" \
    -alias lifegather -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=LifeGather" >/dev/null
fi
[ -n "$PASSWORD" ] || { echo "Set LIFEGATHER_ANDROID_KEYSTORE_PASSWORD" >&2; exit 1; }
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-pass env:LIFEGATHER_ANDROID_KEYSTORE_PASSWORD \
  --ks-key-alias lifegather --out build/LifeGather.apk build/aligned.apk
"$TOOLS/apksigner" verify build/LifeGather.apk
echo "Built android/build/LifeGather.apk (version $VERSION, code $VERSION_CODE)"
