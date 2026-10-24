# iPhone app

Since v0.102.0 there is a small LifeGather app for iPhone (and iPad). Like the
[Android app](ANDROID_APP.md), it opens your own LifeGather server over your
home Wi-Fi, with no HTTPS address, tunnel or extra service to set up. It shows
the same LifeGather you use on the computer; everything stays on your server.

Apple doesn't let iPhones install an app from a downloaded file, so you build
it once on a Mac and send it to your iPhone. This page walks through that. Plan
on about an hour the first time, most of it waiting for downloads.

## What you need

- **A Mac** with the current version of macOS that Xcode needs. Xcode is
  Apple's free app for making iPhone apps (a large download, about 10 GB or more).
- **An Apple Developer Program membership**, $99 a year, on your Apple ID:
  <https://developer.apple.com/programs/enroll/>. Apple can take up to two days
  to approve it. (Without it, an app installed from a Mac stops opening after
  7 days and the "Share to LifeGather" option can't be turned on.)
- **An iPhone** with iOS 15 or newer, on the same Wi-Fi as the NAS running LifeGather.
- **Your server's address**, the one you type on another computer to open
  LifeGather, such as `http://192.168.1.20:8787`. On TrueNAS it is `http://` +
  the NAS's IP address + `:8787`. On a Windows PC, run
  `scripts\Start-Home-Network.cmd` once first (see
  [Windows PC as the server](ANDROID_APP.md#windows-pc-as-the-server)).
- **An email-and-password sign-in** for LifeGather. Google sign-in doesn't work
  inside the app; if you only ever used Google, set one up first (see
  [local account](LOCAL_ACCOUNT_SETUP.md)).

## Step 1: Set up Xcode (one time)

1. Install **Xcode** from the Mac App Store and open it once. Let it install any
   extra parts it asks for; when it asks which platforms to add, tick **iOS**.
2. In Xcode's menu bar choose **Xcode → Settings… → Accounts**, click **+**,
   choose **Apple ID**, and sign in with the Apple ID that has the developer
   membership.

## Step 2: Get the app's code

1. On the Mac, open <https://github.com/bgoldbeck/life-gather>, click the green
   **Code** button, then **Download ZIP**.
2. Open the downloaded ZIP (it unpacks into a folder named `life-gather-main`).
3. In that folder open `ios`, then double-click **`LifeGather.xcodeproj`**. Xcode
   opens the project.

## Step 3: Sign the app with your account (one time)

1. In the left column of Xcode, click the blue **LifeGather** icon at the very
   top.
2. In the middle area, under **Targets**, click **LifeGather**, then the
   **Signing & Capabilities** tab.
3. Tick **Automatically manage signing**, and set **Team** to your name (the
   developer membership, not "Personal Team").
4. Under **Targets**, click **LifeGatherShare** and do the same: **Automatically
   manage signing** on, same **Team**.
5. Wait a few seconds. If Xcode shows a red message that the bundle identifier
   "is not available" or "cannot be registered", someone else already used the
   app's ID:
   - In the left column open **Config → LifeGather.xcconfig**.
   - Change the line `LIFEGATHER_BUNDLE_ID = io.github.bgoldbeck.lifegather` to
     something only you use, for example
     `LIFEGATHER_BUNDLE_ID = com.lisagoldbeck.lifegather` (letters, numbers,
     dots and dashes only).
   - Press **⌘S** to save, go back to **Signing & Capabilities**, and click
     **Try Again** if it is shown. Both targets pick up the new ID.

Both targets should now show no red messages. Xcode registers the app and its
shared "App Group" folder with Apple for you. If a red message mentions **App
Groups** instead, scroll down to the **App Groups** box on the same tab, click
**+**, add `group.` followed by the bundle ID (for example
`group.io.github.bgoldbeck.lifegather`), and make sure it is ticked in both
targets.

## Step 4: Put the app on your iPhone

There are two ways. **A** is quicker for your own iPhone; **B** (TestFlight)
needs no cable and suits installing on family members' iPhones too.

### A. Straight from the Mac, with a cable (simplest)

1. Connect the iPhone to the Mac with a cable. On the iPhone, tap **Trust** and
   enter its passcode if asked.
2. On the iPhone turn on **Developer Mode**: **Settings → Privacy & Security →
   Developer Mode** (near the bottom), switch it on, and let the iPhone restart.
   After the restart, tap **Turn On** and enter the passcode. (If you don't see
   Developer Mode, do step 3 once first; the iPhone shows the option after Xcode
   has seen it.)
3. In Xcode's top bar, click the device name next to **LifeGather** and pick
   your iPhone.
4. Click the **▶** (Run) button. The first time takes a few minutes. LifeGather
   appears on the iPhone's home screen and opens.

An app installed this way keeps working for a year. To renew it, repeat steps
1, 3 and 4. You can unplug the cable once it is installed.

### B. Through TestFlight (no cable, more steps)

TestFlight is Apple's app for installing test versions. Each upload works for 90
days; after that, upload again (steps 2 to 4 below) and the iPhone updates.

1. **Create the app record (one time).** Open <https://appstoreconnect.apple.com>,
   sign in, click **Apps**, then **+ → New App**:
   - Platforms: **iOS**. Name: **LifeGather** (if that name is taken on the App
     Store, add a word, such as "LifeGather Home"; only you will see it).
   - Primary language: **English**. Bundle ID: pick the one ending in
     `lifegather` (the one from Step 3). SKU: `lifegather`.
   - User Access: **Full Access**. Click **Create**.
2. **Make the build.** In Xcode's top bar, click the device name next to
   **LifeGather** and choose **Any iOS Device (arm64)**. Then choose **Product →
   Archive** in the menu bar. When it finishes, the Organizer window opens.
3. **Upload it.** In the Organizer, with the new archive selected, click
   **Distribute App**, choose **TestFlight Internal Only**, and click
   **Distribute**. If Xcode offers to manage the version and build number, say
   yes. Wait for **Upload Successful**.
4. **Wait for Apple.** You get an email when the build "has completed
   processing", usually within 30 minutes.
5. **Invite yourself (one time).** In App Store Connect open the app, then
   **TestFlight**. Next to **Internal Testing** click **+**, name the group (for
   example "Family"), and add yourself. Add the build to the group if it isn't
   there already.
6. **Install.** On the iPhone, install **TestFlight** from the App Store, sign in
   with the same Apple ID, and tap **Install** next to LifeGather.

To add another person, first add them as a user in App Store Connect
(**Users and Access**), then to the TestFlight group. They install TestFlight
on their iPhone and accept the email invitation.

## Step 5: First time on the iPhone

1. Open **LifeGather**. Type your server's address, such as
   `http://192.168.1.20:8787`, and tap **Connect**.
2. The iPhone asks whether LifeGather may **find and connect to devices on your
   local network**. Tap **Allow**. (If the app then says it couldn't reach
   LifeGather, tap **Connect** once more.) Missed it? Turn it on in **Settings →
   Privacy & Security → Local Network → LifeGather**.
3. **Sign in** with your LifeGather email and password.

## Using it

- **Take a photo:** in **Photos** or the assistant's photo picker, tap **Take a
  photo**. The first time, allow camera access. The photo is saved to LifeGather
  straight away.
- **Share into LifeGather:** in Photos, Files, Mail or another app, tap
  **Share** and pick **LifeGather** (the first time you may need to scroll the
  row of apps to the end, tap **More**, and switch LifeGather on). It says
  **Saved for LifeGather**; tap **Done**, then open the LifeGather app. It asks
  whether to keep the files in Photos or Documents (up to 10 files, 8 MB each).
  Shared files wait for an hour. iPhone photos are turned into JPEG pictures on
  the way, because LifeGather keeps JPEG, PNG and WebP photos.
- **Change the server address** (for example a new NAS address): touch and hold
  the LifeGather icon on the home screen and choose **Change server address**.
  The app also offers this when it can't reach the server.
- **Go back a page:** swipe right from the left edge of the screen.
- **Away from home** the app can't reach your server and says so. It works again
  once the iPhone is back on your home Wi-Fi.

Not available in the app yet: **Google sign-in** (Google doesn't allow sign-in
inside apps like this one), connecting Gmail, and downloads such as record
exports. Do those on the computer.

## Updating

LifeGather's pages always come from your server, so most improvements reach the
app without doing anything on the iPhone. The app itself only needs rebuilding
when the `ios` folder changes, or when a TestFlight build is about to expire:
download the code again (Step 2; the signing from Step 3 has to be chosen again
in the fresh copy, and if you changed the bundle ID, change it the same way),
then repeat Step 4. Your server address and sign-in stay.

## Privacy and security

- The app stores only the server address, your sign-in cookie and the usual
  short-lived web cache. Files shared into it wait in a private folder that only
  LifeGather and its Share option can read, until the page saves them (each file
  is deleted as soon as the page has it) or for an hour at most.
- Your home network carries the connection unencrypted (plain `http://`), the
  same as opening LifeGather in a browser at that address. Use it only on a home
  Wi-Fi you trust, and never forward LifeGather's port through your router.
- Links to other websites open in Safari, not inside the app.
- The app asks for the camera only when you take a photo, and for the local
  network so it can reach your server. It asks for nothing else.

## How it works (for maintainers)

The source is in [`ios/`](../ios); see [`ios/README.md`](../ios/README.md). It
works the same way as the [Android app](ANDROID_APP.md#how-it-works-for-maintainers):

- **Same address the server already trusts.** The app relays the iPhone's own
  `127.0.0.1:8787` (Network framework, loopback only) to the address the user
  typed and opens the web app there, so the server sees its default
  `LIFEGATHER_PUBLIC_URL` and none of its sign-in, origin or CSRF checks change.
  An `https://` address is opened directly. App Transport Security allows only
  local networking (`NSAllowsLocalNetworking`); iOS asks once for Local Network
  access. iOS closes the listener in the background; the app reopens it when it
  returns.
- **Camera:** `WKWebView` handles the page's `capture` file input itself.
- **Share:** a Share extension copies up to 10 items (each cut off one byte past
  8 MB so the page reports it as too large; other image types become JPEG with
  their metadata) into the App Group folder, writing `share.json` last. When the
  app becomes active it opens `/?share=<id>` for the newest unclaimed share. The
  page claims it once through the `lifegatherShare` script message handler
  (`window.webkit.messageHandlers`, answered only for the main frame on the web
  origin), then fetches each file once as base64, and saves it through the
  normal Photos or Documents upload, so CSRF, size limits and storage quotas
  still apply. iOS doesn't let a Share extension open its app, so the user opens
  it.

Checked so far: `ios/check.sh` (address rules and the share folder, with the
same cases as the Android checks) passes with Swift 6.0 on Linux; the Xcode
project file parses and lists both targets; the page's iPhone hand-over has unit
tests. The app and Share extension have **not yet been compiled in Xcode or
tried on a real iPhone**, because that needs a Mac.
