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

The reply is stored in the conversation like other Chat replies; no records,
facts, assets or evidence are written and there is no schema change. It keeps:

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

## Not included yet

Gemini research, saving reviewed research findings as evidence on a record,
fetching and reading full manuals, and research started by the AI assistant.

Contracts checked 2026-10-22:
[Claude web search tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool),
[OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search).
Verification uses mock HTTP transports and synthetic providers; no live API key or
paid search was used.
