# Persistent review queue

Review shows pending item proposals and current unresolved identity decisions.
It reads existing durable records, including after restart/restore; it is not a
second copy of chat state. Filters and bounded 25-row keyset pages cover both
kinds. A decision made through Chat or another authorized adapter is reflected
on refresh or reopening the view. Not sure leaves work pending.

Proposals use the same source/quote, corrected-note head, photo provenance,
identifier checks, duplicate preview and explicit confirmation as Chat.
Identity reviews show the exact observation, quote, source, quantity and current
candidate names/opaque identifiers. Choose all-new distinct items, one existing
record per unit, or exclude the observation from inventory. Mixed new/existing
multi-unit selections are deferred. Mention/payment sources cannot create owned
inventory. Neither similarity nor a general image attachment proves identity.

Writes require owned records, session/origin/CSRF, current decision head and an
unchanged candidate set. Current note/photo validation blocks obsolete evidence.
Exact repeated decisions return the same successor; conflicting stale choices
fail with a reload message. The original source, observations and decision/fact
history remain available, including after undo or exclusion. Existing asset
correction tools can undo an accepted association. Since v0.73.0 the queue
offers **Undo** right after a decision, including a dismissal, returning it to
the queue (see [UNDO.md](UNDO.md)). Pending stale proposals remain
visible so they can be rejected and replaced from their current source.

Authenticated typed MCP operations: review_queue, review_identity,
review_identity_resolve, identity_review_undo. App model providers have no write tools. Queue review
requires no AI permission, model key, paid call or background automation. No new
schema migration. Graphify was unavailable on the verification host.
