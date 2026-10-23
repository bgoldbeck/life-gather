# Android app

Since v0.101.0 there is a small LifeGather app for Android phones. It opens your
own LifeGather server over your home Wi-Fi, with no HTTPS address, tunnel or
extra service to set up. It shows the same LifeGather you use on the computer;
everything stays on your server.

## Installing it (one time)

You need: an Android phone (Android 7 or newer) on the same Wi-Fi as the computer
or NAS that runs LifeGather, and the file `LifeGather.apk`.

1. **Find your server's address.** It is the address you type on another
   computer to open LifeGather, such as `http://192.168.1.20:8787`. On TrueNAS it
   is `http://` + the NAS's IP address + `:8787`. (The Windows test preview
   started by `Publish-And-Start` only listens on the PC itself, so phones can't
   reach it; use the TrueNAS install.)
2. **Get the file onto the phone.** On the phone, open
   <https://github.com/bgoldbeck/life-gather/raw/main/android/release/LifeGather.apk>
   to download `LifeGather.apk`, or copy it over from the computer.
3. **Open the file.** Tap the download in the notification or in the **Files**
   app. Android asks whether to allow installs from that app (for example
   Chrome or Files): tap **Settings**, turn on **Allow from this source**, and go
   back. Tap **Install**.
4. **If Google Play Protect warns** that it doesn't recognise the app, tap
   **More details**, then **Install anyway**. The app isn't in the Play Store,
   so Android can't vouch for it; that is expected.
5. **Open LifeGather** from the home screen. Type your server's address and tap
   **Connect**. The app checks that LifeGather answers there and remembers it.
6. **Sign in** with your LifeGather email and password. Google sign-in doesn't
   work inside the app; if you only ever used Google, set up an
   email-and-password sign-in first (see [local account](LOCAL_ACCOUNT_SETUP.md)).

You can turn **Allow from this source** off again afterwards.

## Using it

- **Take a photo:** in **Photos** or the assistant's photo picker, tap **Take a
  photo**. The phone's camera opens; the photo is saved to LifeGather straight away.
- **Share into LifeGather:** in Gallery, Files, Gmail or another app, tap
  **Share** and pick **LifeGather**. LifeGather opens and asks whether to save the
  files to Photos or Documents (up to 10 files, 8 MB each).
- **Change the server address** (for example moving from the PC to TrueNAS):
  press **Back** on LifeGather's first page and choose **Change server address**.
  The app also offers this when it can't reach the server.
- **Away from home** the app can't reach your server and says so. It works again
  once the phone is back on your home Wi-Fi.

Not available in the app yet: **Google sign-in** (Google doesn't allow sign-in
inside apps like this one), connecting Gmail, and
downloads such as record exports. Do those on the computer.

## Updating

A new `LifeGather.apk` installs over the old one and keeps your server address
and sign-in. LifeGather's pages always come from your server, so most
improvements reach the app without a new APK; a new APK is only needed when
the app itself changes. If Android refuses an update because it "conflicts
with an existing package" (a build signed with a different key), uninstall
LifeGather from the phone first, then install the new file; you only type the
server address and sign in again.

## Privacy and security

- The app stores only the server address, your sign-in cookie and the browser's
  usual short-lived cache. Files shared into it wait in the app's private
  storage only until LifeGather saves them, and are deleted after that (or the
  next time the app starts).
- Your home network carries the connection unencrypted (plain `http://`), the
  same as opening LifeGather in a browser at that address. Use it only on a home
  Wi-Fi you trust, and never forward LifeGather's port through your router.
- Links to other websites open in your normal browser, not inside the app.

## How it works (for maintainers)

The source is in [`android/`](../android). It is a plain-Java WebView app with no
Gradle plugin, so it builds from Debian/Ubuntu packages (Google's SDK download
is not needed); see [`android/README.md`](../android/README.md).

- **Same address the server already trusts.** A self-hosted plain-HTTP
  installation accepts sign-in and changes only from its configured
  `LIFEGATHER_PUBLIC_URL`, which must be loopback (`http://127.0.0.1:8787`, the
  default). The app runs a byte-for-byte relay on the phone's own
  `127.0.0.1:8787` to the address the user typed and opens the web app there,
  so the server sees exactly its own address and none of its sign-in, origin or
  CSRF checks change. The relay listens on the phone's loopback interface only.
  An `https://` address is opened directly, without the relay.
  So the server must keep the default public URL and be reachable on the home
  network (TrueNAS publishes `0.0.0.0:8787`; the Windows test-login preview
  from `Start-Test-Login` listens on the PC only).
- **Camera:** the page's ordinary `capture` file input starts the phone's camera
  app, which writes into a private file the app grants it one photo at a time.
  The app does not ask for the camera permission.
- **Share:** Android's share sheet hands files to the app, which copies them
  (at most 10, each cut off one byte past 8 MB so the page reports it as too
  large) and opens `/?share=<random id>`. The page's existing share flow asks
  the app for that share's list once through `window.LifeGatherAndroid`,
  fetches each file from an app-answered `/__lifegather-android/share/...`
  address (never sent to the server), and saves it through the normal Photos or
  Documents upload, so CSRF, size limits and storage quotas still apply.
- The app's version follows `backend/src/lifegather/version.py`. Phones accept
  an update only when it is signed with the same key, so keep the signing key
  (see `android/README.md`).

Checked so far: the APK builds, signs (APK Signature Scheme v2/v3) and passes
`apksigner verify`; the relay was exercised on a computer (address preserved,
5 MB upload, keep-alive); the page's share hand-over has unit tests. It has not
yet been tried on a real Android phone.

## iPhone

Not built yet. An iPhone version needs:

- **An Apple developer account** ($99 a year) and a Mac with Xcode to build and
  sign it. Without the paid account an app installed from Xcode stops working
  after 7 days.
- **A way to install it:** TestFlight (up to 90 days per build, invite by email)
  or App Store review. iPhones can't install an app from a downloaded file.
- **The same wrapper idea** in Swift: a `WKWebView`, the server-address screen,
  and the same loopback relay (iOS allows an app to listen on `127.0.0.1` while
  it is open). Plain-HTTP home addresses need an App Transport Security
  exception (`NSAllowsLocalNetworking`), and iOS asks once for **Local Network**
  permission.
- **Camera** works through the same file input. **Share to LifeGather** needs a
  separate Share Extension that hands files to the app, because iPhone Safari
  has no web share target.

Until then, iPhones can use LifeGather in Safari at the server's home address.
