# Installable web app (home screen install)

Since v0.95.0 LifeGather can be installed to a phone, tablet or computer home
screen as an app. It is the same web app in its own window, with the LifeGather
icon and no browser address bar. There is no app store and nothing separate to
update: every release on the server reaches the installed app too.

## Installing

The browser only offers installation when LifeGather is opened over **HTTPS**
(or on `localhost` on the server itself). Then:

- **iPhone or iPad (Safari):** tap Share, then **Add to Home Screen**.
- **Android (Chrome):** open the menu and tap **Install app** (or **Add to Home
  screen**). Chrome may also offer an install banner.
- **Computer (Chrome or Edge):** click the install icon at the right of the
  address bar, or use the menu's **Install LifeGather**.

Sign in inside the installed app. On iPhone the installed app keeps its own
sign-in, separate from Safari, so you sign in once more after installing.

## What is stored on the device

The app's service worker (`/sw.js`) stores exactly two files: a small "Can't
reach your LifeGather server" page and the icon it shows. It never stores pages,
API responses, sign-in responses, photos, documents, chat or anything else from
your account. Pages always load from your server; the stored page appears only
when the server cannot be reached. Signing out therefore leaves nothing of yours
behind, and two people using the same phone cannot see each other's records
through the app's storage.

Releases keep working as described in [versioning](VERSIONING.md): the app's
HTML is never served from the service worker, the worker file itself is always
checked against the server, and the existing "new version" notice still offers
an ordinary reload. A new worker replaces the previous one's stored files.

## Sharing files into LifeGather (Android)

Since v0.96.0 an installed LifeGather on Android appears in the share menu of
other apps (Photos, Files, Gmail, a scanner app and so on). Share a receipt
photo or a manual and LifeGather opens with a **Shared to LifeGather** card:

- Photos (JPEG, PNG, WebP) go to **Photos**; choose Photo, Receipt or Nameplate
  for each. Documents (PDF, DOCX, XLSX, TXT, MD, CSV) go to **Documents**.
- Nothing is saved until you press **Save**. **Discard** drops the files.
- Up to 10 files per share, each up to 8 MiB, counted against your account's
  storage limit like any other upload. Saving makes no AI request.

How the files travel: Android posts them to the app's service worker, which
keeps them in memory (never in the browser's cache or IndexedDB) for at most
five minutes and hands them to the open LifeGather page once. The page then
uploads them with your normal signed-in session. If you are signed out, sign in
with email and password on the card that opens and the files are still there;
after a Google sign-in, share them again. If the service worker is not running
(for example right after clearing site data), LifeGather opens with "share the
files again" and nothing is stored.

LifeGather must be installed (see above) before Android lists it as a share
target. **iPhone and iPad** do not support sharing into web apps; use the
upload buttons in Photos and Documents there.

## Self-hosted: getting an HTTPS address

On the home network LifeGather is usually opened as `http://<nas-address>:8787`.
That works in any browser, but phones will not install it, because browsers
only allow installable apps on HTTPS. To install it you need an HTTPS address
for your own server. The options, compared in [remote access](REMOTE_ACCESS.md):

1. **Cloudflare Tunnel with your own domain (recommended).** A small
   `cloudflared` container next to LifeGather connects out to Cloudflare, which
   serves `https://life.<your-domain>` with a valid certificate. No router port
   forwarding, and the phone needs no extra app. It also makes LifeGather
   reachable away from home. Cloudflare sees the traffic as it passes through
   (see the trade-offs in remote access). Follow Cloudflare's
   [tunnel setup](https://developers.cloudflare.com/tunnel/get-started/) and
   point the hostname at `http://<lifegather-service>:8787`.
2. **Tailscale Funnel or Tailscale Serve.** Gives an HTTPS `*.ts.net` address
   without buying a domain. Serve keeps it private to your own tailnet (each
   phone needs the Tailscale app); Funnel makes it public.
3. **Your own reverse proxy** (for example Caddy or Nginx Proxy Manager on the
   NAS) with a certificate for a domain you own. Needs DNS and usually router
   port forwarding, unless it is used only inside the home network.

Whichever you choose, when LifeGather is reached through a proxy or tunnel:

- Set `LIFEGATHER_PUBLIC_URL` to the HTTPS address and add its Google sign-in
  callback (`https://<address>/auth/google/callback`) in Google Cloud, as in
  [Google login](GOOGLE_LOGIN.md). Set `LIFEGATHER_TRUSTED_PROXIES` to the
  proxy or tunnel container's address so sign-in limits see real visitors.
- Keep caching off for `/api/`, `/auth/` and chat streams at the proxy;
  LifeGather already marks them `no-store`.

A plain `http://` LAN address, or an HTTPS address with a self-signed
certificate the phone does not trust, will not install. The browser still
works there; only the home-screen app needs a trusted HTTPS address.

## Hosted site

The hosted Cloudflare deployment ([test site](CLOUDFLARE_TEST_SITE.md)) is
already HTTPS, so installing works there with no extra steps.

## Checking it

In Chrome on a computer, open DevTools, then Application: **Manifest** should
list LifeGather with its icons and no errors, and **Service workers** should
show `/sw.js` as activated. **Cache storage** should hold only
`lifegather-shell-v1` with `/offline.html` and `/icons/lifegather-192.png`.
