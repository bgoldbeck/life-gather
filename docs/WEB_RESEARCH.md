# Web research for manuals and specifications

Phase 2 item 5 of the [feature plan](FEATURE_PLAN.md#phase-2-evidence-intake-and-useful-recall):
on request, look up manuals, specifications and parts information on the public
web when local evidence is not enough, with dated, cited sources.

## Scope (smallest slice)

- A new Chat action, **Research manuals (web)**, sends one research request to the
  selected OpenAI or Claude connection with that provider's own web search tool
  enabled. Google Gemini connections are refused for research for now.
- Only the text the user typed is sent by default. The selected record's saved name
  and details are added **only** when the user ticks *Share this record's saved
  details* for that request. Nothing else from memory, photos, documents or email
  is ever sent. The existing external-AI permission, credential checks, daily
  request limit, cancellation and no-retry rules still apply.
- The reply keeps: the date and time the research ran, the search queries the
  provider reported, whether record details were shared, and each cited source's
  URL, title, provider-reported page date (or "date not reported") and the cited
  excerpt. An answer without at least one valid web citation is discarded.
- Every reply carries a fixed identity note: web results describe a product model,
  not the user's own item; they do not establish ownership, purchase details or
  parts compatibility.
- Research is read-only: it saves no facts, assets or evidence. The result is kept
  in the conversation transcript like other chat replies (no schema change).

## Acceptance checks

- Service tests with mock HTTP transports for Claude (`web_search_20250305`) and
  OpenAI (`web_search`): citations, dates, queries, usage, uncited answers,
  pause/incomplete responses, provider errors, invalid URLs and size limits.
- Runner tests: record details are absent unless shared; sharing requires a
  selected record; Gemini is refused before any usage is reserved; consent and
  credential rechecks hold.
- UI test: choosing the action shows what will be sent, the share checkbox, and the
  rendered dated sources and identity note.
