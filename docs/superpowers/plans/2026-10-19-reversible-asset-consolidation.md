# Reversible two-record asset consolidation

## Baseline and goal

Start from main 426257400e19e5cfbaa01ad09a7a51e0f3d1a754, v0.47.0,
migration 0022_change_origins. Remote main is the only branch and there are no
open PRs at kickoff. The comparison and discovery-batch services already exist;
neither consolidates manual statements, aliases, galleries or arbitrary relations.

Let the authenticated owner explicitly identify two existing asset records as the
same physical item, choose a primary record and inspect one usable current item
without deleting evidence, history, original IDs or historical chat citations.

## Bounded design

- Two unconsolidated assets per operation; no bulk matching, chains, automatic AI
  approval, cross-account operation, purchase merge or financial arithmetic.
- Reuse the complete current-record comparison and its limits. Preview contains
  exact affected state and both versions; apply revalidates inside one serialized
  transaction. A partial preview is never authority to write.
- Add an owner-constrained, versioned consolidation association and immutable
  explanation/audit history. Keep original sources/fact versions and identifiers.
  Current views resolve the association centrally; historical reads keep their
  recorded context. Show conflicting statements rather than choosing values.
- Preserve separate receipt units and purchase identities. Refuse sibling physical
  units, incompatible identifiers and existing replacement relationships.
- Make Assets, Profiles, galleries, graph/recall and subsequent matching respect the
  same canonical association. Old IDs stay inspectable. Preserve pagination and
  owner-scoped bounded query contracts.
- Stable request replay, stale-preview rejection, transactional rollback and
  guarded reversal. Refuse reversal after dependent changes rather than overwrite.
- Include association/history in explicit record portability and snapshot recovery;
  document any format revision and preserve existing exports.
- Explicit responsive UI from comparison, explanation, primary choice, confirmation,
  retry/error handling and reversal with links to preserved original records.

## Acceptance

Synthetic manual-spec/photo record plus receipt record consolidate into one current
asset; its source quotes, aliases, conflicting facts, units and purchase claims remain
inspectable. Later import enriches the selected asset. Reversal restores separation
when unchanged, with historical citations still readable throughout.

Test service/API/MCP owner isolation and CSRF, incompatible identities, sibling units,
replacement conflicts, stale reads/writes, bounded completeness, same/different
request retries, concurrency, rollback, two time dimensions, export and migration/
snapshot preservation. Exercise UI confirmation, lost response, late navigation,
conflicts and narrow layout. Run backend/frontend suites, strict typing, lint,
format and builds. Refresh code-only source graph/HTML if available.

## Delivery and limits

Publish this scope before implementation, then complete the repository's verified
source/PR release sequence. Check main and open work again before delivery.
Container verification/publication requires available Docker tooling; never claim
publication from a source merge and never redeploy a running installation.
Check account usage between milestones and stop near 5 percent remaining.
No live personal data, mailbox scans or model calls are part of development.
