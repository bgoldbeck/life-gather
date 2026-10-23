# Reconnect prompts for expired sign-ins

Status: released as v0.85.0.

## Problem

An expired or revoked Gmail grant surfaces as a generic "Mailbox request failed"
scan error, and AI connections always show as "unverified" in Power Center even
after a provider refuses the saved key. Nothing tells the person which connection
to fix or gives them a direct way to fix it.

## Scope

1. Record the last observed sign-in state on each saved credential (migration
   `0036_credential_auth_state`: nullable `auth_state` `working|reconnect` and
   `auth_checked_at`). Metadata only; secrets stay encrypted and unread.
2. Gmail: a token refresh answered with `invalid_grant`, or a Gmail API `401`,
   marks the mailbox credential `reconnect` and fails the scan with a safe
   "Gmail access expired or was revoked. Reconnect Gmail" message. A successful
   refresh marks it `working`. Reconnecting through Google consent clears it.
3. AI: a `401`/`403` from OpenAI, Claude or Gemini (chat, research, photo
   reading, Gmail discovery, receipt suggestions) marks that credential
   `reconnect`; a successful request marks it `working`. Replacing the key
   clears the state back to unverified.
4. Power Center shows a refused connection as failed with a **Reconnect**
   button; a recently working AI connection shows as working instead of
   "unverified". Scans shows Reconnect on a failed scan whose mailbox needs it.
   Chat shows Reconnect on the failed reply. Gmail Reconnect starts Google
   consent in one click; AI Reconnect opens Settings on that key's Replace form.

## Not in scope

No background probes or remote health checks (Power Center stays local-only),
no automatic retries, no change to what data is sent to providers.

## Acceptance checks

- Backend tests: Gmail `invalid_grant` and `401` mark the credential and give
  the reconnect message; AI `401`/`403` mark the credential in chat; replace and
  reconnect clear the state; Power Center reports reconnect/working states.
- Frontend tests: Reconnect buttons in Power Center, Scans and chat start Gmail
  consent or open the Replace form.
- `pytest`, `ruff`, `mypy` from `backend/`; `npm test`, `lint`, `build` from
  `frontend/`.
