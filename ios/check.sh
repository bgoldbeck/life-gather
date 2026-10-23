#!/usr/bin/env bash
# Checks the iPhone app's address and share-inbox logic with any Swift
# toolchain (Xcode's on a Mac, or swift.org's on Linux), and that the app's
# version matches LifeGather's single version source. No iPhone or Xcode needed.
set -euo pipefail
cd "$(dirname "$0")"

VERSION=$(sed -n 's/^__version__ = "\([0-9]*\.[0-9]*\.[0-9]*\)"$/\1/p' ../backend/src/lifegather/version.py)
APP_VERSION=$(sed -n 's/^MARKETING_VERSION = \(.*\)$/\1/p' Config/LifeGather.xcconfig)
if [ "$VERSION" != "$APP_VERSION" ]; then
  echo "ios/Config/LifeGather.xcconfig has MARKETING_VERSION $APP_VERSION; version.py says $VERSION" >&2
  exit 1
fi

mkdir -p build
swiftc -O -o build/checks Shared/ServerAddress.swift Shared/ShareInbox.swift Tests/main.swift
build/checks
