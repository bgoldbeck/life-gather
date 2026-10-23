# Search everything

Available in v0.68.0. The search box in the top bar looks across your own
records at once, so you no longer need to know which page holds something.

Type at least two characters. Results appear after a short pause, grouped as:

- **Assets**: physical items by name. A merged duplicate appears once, under the
  record that was kept.
- **People, places and other records**: other graph records by name.
- **Photos**: by file name. Deleted photos are not shown.
- **Documents**: by file name or reviewed text. Deleted documents are not shown.
- **Sources**: the current text of saved notes, transcriptions, reviewed
  document text and imported email evidence. Earlier versions of a corrected
  note are left out; Memories' history view still shows them. Deleted memories
  are excluded using their deletion receipt, including searches for words in
  the deletion notice. Active notes containing those words still appear.

Every word you type must appear, in any order; matching ignores case. Characters
such as `%` and `_` are matched literally. Up to six results per group are shown;
use more words to narrow them. Searches of more than eight words or 200
characters are refused.

Choose a result to open it where it lives: assets on Assets, other records on
Graph, photos on Photos, documents on Documents. A source that belongs to a photo
or document opens that original; other sources open in Memories with the original
evidence shown. Use the arrow keys to move through results, Enter to open one and
Escape to close the list.

A photo's details now list the assets it is attached to, each with an **Open**
button that goes to that asset.

## Privacy and limits

Search reads only your own records and makes no AI or network request. It uses
plain case-insensitive matching on the server rather than a database-specific
text index, so it behaves the same on SQLite and PostgreSQL storage. There is no
ranking beyond grouping and recency; very large libraries may need a dedicated
index later. Maintenance tasks and purchase records are not searched yet; open
them from their asset.

`GET /api/search?q=<words>&limit=<1-10>` returns
`{"query", "items": [{"kind", "id", "title", "detail", "photo_id"?, "document_id"?}]}`
for a signed-in session. `GET /api/photos/{id}/assets` lists a photo's attached
assets.
