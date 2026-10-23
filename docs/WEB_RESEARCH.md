# Web research for manuals and specifications

Version 0.67.0 delivers Phase 2 item 5 of the
[feature plan](FEATURE_PLAN.md#phase-2-evidence-intake-and-useful-recall): on
request, look up manuals, specifications and parts information on the public web
when local evidence is not enough, with dated, cited sources.

## Using it

In Chat choose **Research manuals on the web**, pick an OpenAI or Claude
connection and model, and type what to look up, for example "Owner's manual and
filter part number for Bosch SHX878WD5". While a record is open, an unticked box
offers to share that record's saved name and details for this one request.

## What is sent

- Always: the text you typed and today's date.
- Only when you tick the share box: the open record's name, kind and saved
  profile details, read the same way as the AI assistant's selected-record
  context. The request fails if the record changed after you opened it, so the
  details sent are the ones you saw. The box clears after every request and when
  you open a different record.
- Never: other memories, notes, purchases, photos, documents, email or
  credentials.

The existing rules still apply: external AI must be enabled in Settings, the
connection is rechecked before the call, a research request counts as one of the
20 daily AI requests, there is no automatic retry and Stop cancels it. The
provider's web search is billed by the provider in addition to tokens.

## Providers

- Claude: Messages API with the server tool `web_search_20250305`, at most three
  searches. No structured output is requested because web-search citations are
  returned on text blocks.
- OpenAI: Responses API with the `web_search` tool, `store: false`, at most three
  tool calls.
- Google Gemini: not supported yet; refused before any usage is counted.

Responses are capped at 1 MiB, the read timeout is 55 seconds inside the 65-second
turn bound, redirects and environment proxies are disabled, and any unexpected
block type, paused or incomplete response, or invalid usage fails with a redacted
error.

## What is kept

The reply is stored in the conversation like other Chat replies; nothing is
written to your records unless you save a source (below). The reply keeps:

- `researched_at`: when the request started (UTC).
- `queries`: the searches the provider reported running.
- `shared_record`: the shared record's id and name, or null.
- `sources`: up to ten cited pages, each with URL (http/https only), title,
  `published` (the page date the provider reported, or null, shown as "date not
  reported") and up to three excerpts. Claude excerpts are quoted from the page;
  OpenAI excerpts are the part of the answer that cites the page.
- `identity_note`: web results describe a product model, not your own item, and
  do not establish ownership, purchase details or parts compatibility.

An answer with no valid web citation is discarded and replaced with a "no cited
web sources" message. Web pages are treated as untrusted data in the instruction.

## Saving a source to an asset

Version 0.83.0. While an asset is open, each cited source in a finished research
reply shows **Save to <asset name>**. Nothing is saved until you press it, and only
that one source is saved. With no asset open, the reply says to open one first.

- The browser sends only which reply, which cited URL and which asset. The server
  copies the URL, title, page date, excerpts, research time, provider, model and
  your typed request from the stored reply, so a saved finding always matches
  what you were shown. A URL that the reply did not cite, a reply that is not a
  finished web research reply, another account's reply or a record that is not
  a physical asset is refused.
- Saving the same page to the same asset again keeps one finding and says it was
  already saved. Version 0.84.1 keeps a receipt for every accepted request,
  including duplicate saves. Reusing a request ID with a different reply, URL or
  original asset is refused. Exact retries return the original finding even
  after consolidation changes or conversation deletion. If that finding was
  removed, the UI says so and offers **Save again** as a new explicit action;
  a retry never revives removed evidence.
- The asset page lists findings under **Saved web research**, newest first, with
  the source link, page date (or "Page date not reported"), research and save
  times, the request and excerpts. Findings saved to either record of a
  consolidated pair show on both.
- **Remove** asks for confirmation, hides the finding and keeps the row with its
  removal time as history. The page can be saved again afterwards.
- Findings are a copy: deleting the conversation keeps them.
- Findings describe a product model. They are not ownership, purchase or
  parts-compatibility facts and do not change the asset's details.

Storage: migration `0034_research_findings` adds the owner-scoped
`research_findings` table with the same row-level security policy as every other
account table. Migration `0035_research_save_receipts` adds owner-bound request
receipts with row-level security. HTTP: `POST /api/research-findings`,
`POST /api/research-findings/remove`, `GET /api/research-findings/assets/{asset_id}`.
MCP: read-only `asset_research_findings`. Personal records format 6 includes the
findings and save receipts; formats 4 and 5 archives still restore.

## Recall saved findings in Chat

Version 0.86.0. The **AI assistant** can select a read-only tool to answer later
questions about an asset's saved research. Replies show dated saved excerpts,
source links and asset navigation; generated answer excerpts remain labeled.
The selection is bounded to five active findings across a request and may be
incomplete. Existing external-AI permission applies. See
[assistant recall](AI_ASSISTANT.md#saved-web-research-v0860) for privacy, history
and evidence restrictions. This reads saved findings and does not run research.

## Not included yet

Gemini research, fetching and reading full manuals, research started by the AI
assistant, and turning a finding into a sourced field value on the asset.

Contracts checked 2026-10-22:
[Claude web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool),
[OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search).
Verification uses mock HTTP transports and synthetic providers; no live API key or
paid search was used.

Legacy limit: before v0.84.1, only a finding's first request ID was stored. Its
first replay must still name the same current physical identity; it then gains
an exact receipt. Historical duplicate request IDs and the original target
before consolidation cannot be reconstructed. Receiptless format 5 archives
retain this limit; formats 4 and 5 remain accepted for restore.
