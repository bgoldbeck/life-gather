# Undo

Phase 3 broadens undo only for operations that can be reversed without losing
evidence or history. An undo is itself a new recorded change: the original
decision, link or schedule state stays in history and audit, nothing is erased.

## Undo added in this increment

- **Review queue identity decisions.** After you choose *Create new item*,
  *Link to existing item* or *Dismiss* on an identity match, an **Undo** button
  appears. Undo records a new decision that returns the observation to the review
  queue, so you can decide again. Before this, a dismissed match could not be
  brought back at all. Undo is refused if anything changed the decision since
  (a later correction, reassociation or another undo); reload and use the item's
  own actions instead. Private HTTP `POST /api/reviews/identities/undo` and MCP
  tool `identity_review_undo` share the same owner checks; an exact retry is safe.
- **Removing a photo from an item.** The removal only deletes the link, never the
  photo, so **Undo** re-attaches the same photo to the same item.
- **Pausing or resuming a scan schedule.** **Undo** switches it back.

The Undo button stays until you leave the view or make another change there.

## Already reversible elsewhere

These already have explicit, recorded reversals with their own confirmation and
are unchanged: undoing an automatic confirmation/association and reassociating a
unit (Assets → *Change to make*), reversing a consolidation, restoring a moved
evidence batch, withdrawing a recorded replacement and withdrawing purchase
evidence. Field values are corrected by recording a new version from history.

## Deliberately not undoable

- Deleting a photo, document or chat conversation, and chat retention: the stored
  originals are removed, so an undo would have nothing to restore.
- Disconnecting a mailbox or deleting an AI connection: the credentials are
  revoked or discarded and must be added again.
- Completed scans, chat turns and provider requests: data already sent to a
  provider cannot be recalled.
