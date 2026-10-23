# Photo galleries

Group saved photos by event, such as "Moving day" or "Kitchen remodel". This is
optional backlog item "Photo event galleries" in [the feature plan](FEATURE_PLAN.md).

## Scope

- A gallery is a name chosen by the account owner, with an optional event date
  the owner types in. LifeGather never guesses a gallery's date or contents
  from photo metadata (photo previews have their metadata removed anyway).
- A photo can be in any number of galleries. Galleries never establish
  ownership, purchases or any other fact; they only group photos.
- Removing a photo from a gallery, or deleting a gallery, keeps every photo.
  Deleting a photo removes it from every gallery.
- Galleries are private to one account, like every other record (row security
  plus account-scoped queries).
- Galleries and their photo lists are part of the personal record download
  (records format 7) and personal archive restore. Older archives still
  restore.
- Account deletion and source erasure remove gallery membership with the
  photos they remove, by following the database's own foreign keys.

## Where it shows

Photos view:

- A gallery bar above the photo grid: All photos, each gallery (name, date,
  photo count), and New gallery.
- An open gallery shows only its photos, with Add photos (pick several saved
  photos at once), Edit and Delete gallery.
- Photo details list the galleries that hold the photo, with Add to gallery
  and Remove from gallery.

Item (asset) photo panels are unchanged.

## Limits

100 galleries per account, names up to 80 characters, up to 50 photos added
in one request. Each account already holds at most 200 photos.

## Interfaces

HTTP, under `/api/photo-galleries`:

| Method and path | Purpose |
| --- | --- |
| `GET /api/photo-galleries` | List galleries with photo counts and a cover photo |
| `POST /api/photo-galleries` | Create (`title`, optional `event_on` as `YYYY-MM-DD`); repeating the same name and date returns the existing gallery |
| `POST /api/photo-galleries/{id}/update` | Rename or change the date (`expected_updated_at` guards concurrent edits) |
| `POST /api/photo-galleries/{id}/delete` | Delete the gallery, keep its photos |
| `POST /api/photo-galleries/{id}/photos` | Add up to 50 photos (`photo_ids`); already added photos are skipped |
| `POST /api/photo-galleries/{id}/photos/remove` | Remove one photo from the gallery |
| `GET /api/photos?gallery_id=…` | Photos in one gallery |
| `GET /api/photos/{id}/galleries` | Galleries holding one photo |

MCP: `photo_gallery_list` (read-only), and `photo_list` accepts `gallery_id`.

## Acceptance checks

1. Create, rename, date and delete a gallery; deleting keeps the photos.
2. Add several photos at once, remove one, and see the open gallery and photo
   details update.
3. Deleted photos disappear from galleries and counts.
4. Another account cannot list, read, change or add to the gallery, and cannot
   add its own photos to it (HTTP, MCP and row security).
5. Record export and archive restore keep galleries; a format 6 archive still
   restores.
6. Light and dark themes, desktop and phone widths.
