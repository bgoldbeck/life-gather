# Sign-up bot checks and terms of use

Phase 5.5 (hosted account lifecycle) of the [feature plan](FEATURE_PLAN.md).
Both protections are **off by default**, so a self-hosted installation behaves
as before until its owner turns them on. Account deletion is covered separately
in [account deletion](ACCOUNT_DELETION.md).

## Bot checks (Cloudflare Turnstile)

Set both values to turn the check on:

```
LIFEGATHER_TURNSTILE_SITE_KEY=0x4AAAAAAA...
LIFEGATHER_TURNSTILE_SECRET_KEY=0x4AAAAAAA...
```

Create the widget in the Cloudflare dashboard (Turnstile, free) for the
installation's hostname. With both keys set:

- The **Create account** and **Forgot password?** email forms show the
  Turnstile widget, and the server verifies each token with Cloudflare's
  `siteverify` endpoint before it sends any email. A missing, expired, reused or
  failed token is refused with "Complete the bot check and try again".
- If Cloudflare cannot be reached, the request is refused rather than allowed
  through (fail closed); existing accounts can still sign in.
- Password sign-in and Google sign-in do not show the widget. Password sign-in
  already has persistent per-address and per-client limits, and Google runs its
  own abuse checks before an account is created.

Setting only one of the two keys is a configuration error at startup.

## Terms of use

Set a version label to require acceptance:

```
LIFEGATHER_TERMS_VERSION=2026-10-23
# Optional: your own text instead of the bundled placeholder
LIFEGATHER_TERMS_FILE=/config/terms.md
```

With a version set, every account, new or existing, must accept that version
before it can use the app. The first screen after sign-in (Google or email)
shows the terms with an "I agree" checkbox. Until the person accepts:

- every app route and the MCP endpoint answer 403 "Accept the terms of use to
  continue";
- they can still read the terms, sign out, or delete the account they just
  created.

The accepted version and time are stored on the account (`users.terms_version`,
`users.terms_accepted_at`). Changing `LIFEGATHER_TERMS_VERSION` asks everyone
to accept the new version on their next request. Removing the setting turns the
check off again; recorded acceptances are kept.

The bundled text in `backend/src/lifegather/auth/terms_placeholder.md` is a
**placeholder, not legal advice**. Replace it with terms and a privacy notice
reviewed for the service you run, either by editing that file before building
the image or by pointing `LIFEGATHER_TERMS_FILE` at your own file. The text is shown
as plain text, not rendered HTML.

Recovery bundles do not carry these four settings: like proxy and storage
settings they belong to the host that runs a restored installation. Recorded
acceptances are database rows and are restored with everything else.
