# Remote phone access: recommended design

Research date: 2026-10-17. Recommendation only; nothing exposed or installed.

## User requirements

Open LifeGather from a phone browser, sign in with Google, take/attach a photo with a message, and receive a response. No companion VPN installation on the phone. Keep self-hosted storage and private per-user records. User does not currently own a domain. Do not purchase a domain, select a paid plan, rebuild/upload images, or expose the unauthenticated preview as part of this research.

## Recommendation: named Cloudflare Tunnel and an owned domain

Use a subdomain such as `life.example.com` (illustration, not an actual chosen address). Run a separate `cloudflared` connector alongside LifeGather on the NAS. Map that hostname to LifeGather's private container service on port 8787 after the updated image is deployed. On a shared Docker network the target would be `http://backend:8787`, not the connector container's `localhost`.

Flow: phone browser → public HTTPS hostname → Cloudflare → outbound-established tunnel → LifeGather → authenticated user's private data. The NAS connector initiates the connection, avoiding inbound router port forwarding. The phone needs no Cloudflare/VPN client. The server and home internet must remain online; upload and response speed still depend on home bandwidth.

Cloudflare Tunnel is available on the Free plan. Domain registration/renewal is a separate recurring cost; do not promise a zero-cost deployment or quote a price before a domain is selected. Avoid enabling paid add-ons. This setup serves the web app, not bulk media hosting; review current service terms before expanding to large-file/video delivery.

The URL is publicly reachable. Privacy comes from application authentication and ownership enforcement, not from hiding the URL. Use LifeGather's Google login rather than requiring an additional Cloudflare Access login by default, consistent with open Google registration.

Cloudflare terminates HTTPS and processes the proxied HTTP traffic, so this is not phone-to-NAS end-to-end encryption hidden from Cloudflare. User records remain stored by LifeGather, but traffic passes through a third-party processor. If that trust model is unacceptable, evaluate a direct HTTPS reverse proxy instead; do not describe all tunnel providers as having the same TLS properties.

## Alternatives considered

- Tailscale Funnel: provides a stable HTTPS `*.ts.net` address with no client required on visiting phones; Tailscale runs on the hosting side. It has non-configurable bandwidth limits and no custom hostname support through Funnel itself. A possible no-domain pilot after authentication, but production Google OAuth domain/branding suitability must be checked before committing to the hostname. Do not equate public application users with members of the host's private tailnet.
- Cloudflare Quick Tunnel: temporary random hostname, testing-only, and no Server-Sent Events support. Unsuitable for the planned stable Google callback and streaming-chat deployment.
- Direct HTTPS reverse proxy: avoids Cloudflare handling application traffic, but requires a suitable public connection, DNS/certificate management, and usually router forwarding. Carrier-grade NAT can prevent this approach. Not the simplest default for this user.

## Application work before remote exposure

1. Finish Google login, server-managed Secure/HttpOnly sessions, CSRF protection, and strict two-user isolation, including uploads and background jobs. Configure the exact HTTPS callback and public base URL. Verify current Google branding/domain requirements; registration in LifeGather and Google's OAuth publishing requirements are separate concerns.
2. Use one HTTPS origin for UI/API. Validate Host/Origin and trust forwarded headers only from the configured proxy. The existing image disables proxy-header handling, so secure scheme/redirect handling needs explicit implementation and testing.
3. Require ownership checks on every upload/download and generated preview. Store files outside static assets. Apply file/content limits and prevent shared caching of private responses. Define clear file retention and privacy deletion behavior.
4. Use a proposed initial 20 MB per-file limit with image resizing where appropriate; confirm this in the capture implementation plan. Cloudflare's documented Free-plan maximum request body is 100 MB and includes multipart overhead. Do not treat that upper bound as an application upload policy. Return understandable errors and avoid duplicate ingestion on retries.
5. Keep the connector token out of Git and logs. Give the connector only the network access needed for LifeGather. Prefer a tunnel-only service without host-published app ports; retain a documented private LAN-only alternative if required. Never expose the NAS administration UI, Docker API, or filesystem.
6. Configure caching rules to bypass authenticated pages, chat streams, API responses, uploads, and documents. Test streamed chat through the named tunnel; do not assume a working homepage proves streaming works.

## Phone capture design

Start with responsive chat supporting camera/file-picker upload, preview, optional typed note, explicit Send, visible progress, retry, and Cancel. Keyboard dictation can provide voice-to-text without a separate speech integration. Photos go directly to the signed-in user's LifeGather server, not email. External AI processing follows the user's configured permissions.

An installable PWA/home-screen experience and direct camera/microphone APIs need HTTPS in this deployment. Native share-menu receiving support varies; keep ordinary attachment upload as the universal fallback and test iPhone Safari and Android Chrome separately. Do not promise reliable background upload, offline capture, or share-target support on all phones without implementation-specific tests.

## Acceptance before launch

- On cellular data with no VPN app, sign in, take/select a photo, submit a note, and inspect the sourced result in the same account.
- Confirm exact OAuth callbacks, secure session cookies, logout/expiry, and rejection of forged Host/Origin/proxy headers.
- Verify two accounts cannot retrieve each other's photos, sources, search results, graph records, or cached responses.
- Test streaming, upload-limit errors, interrupted uploads, retry idempotency, and connector/NAS restart recovery.
- Confirm no router forwarding was added and NAS administration remains unreachable through the tunnel. Show actionable behavior when the home server is offline.

## Next decisions

Choose and approve a domain's recurring cost and Cloudflare's traffic-processing role. Then prepare a bounded auth/capture implementation plan. Tunnel configuration comes after those acceptance gates; do not enable it now. Each independent self-hosted installation controls its own hostname, tunnel, and OAuth deployment configuration.

## Official sources

- [Cloudflare Tunnel availability and architecture](https://developers.cloudflare.com/tunnel/)
- [Tunnel setup](https://developers.cloudflare.com/tunnel/get-started/)
- [Published hostname routing](https://developers.cloudflare.com/tunnel/concepts/routing/)
- [Quick Tunnel limitations](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
- [Upload-size limits](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/)
- [Tailscale Funnel behavior and limitations](https://tailscale.com/docs/features/tailscale-funnel)
- [Google OAuth verification requirements](https://support.google.com/cloud/answer/13464321)
- [PWA HTTPS requirements](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)
- [Share-target support](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/share_target)
