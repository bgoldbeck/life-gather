# Timeline and dashboards

Status: delivered in v0.104.0 (2026-10-23).
Lisa chose optional backlog item "Rich timelines/dashboards" on 2026-10-23,
including money dashboards.

## Scope

A new **Timeline** page that reads existing private records. It adds no new
store of truth and no schema change; charts are views over validated records.

- **Money dashboard.** Spending by month for the last 6, 12 or 24 months, one
  chart per currency (currencies are never converted or mixed). Sums only
  reviewed receipt line totals (the current revision of each confirmed
  purchased line whose receipt source still exists). Lines without a total or
  without a purchase date are counted and shown as such, never guessed.
  Order/payment totals from Purchases stay per order and are not added in, so
  one purchase is never counted twice.
- **Activity chart.** Per month counts of assets added, documents and photos
  saved, maintenance completed and items bought.
- **Month timeline.** Every dated event in one month, newest first: purchases
  (stated purchase dates), order evidence dates, maintenance completed and due,
  assets, documents and photos added. Each event says whether its date was
  stated in a source or is when LifeGather recorded it, and opens its record.
- **Coming up.** Open maintenance that is overdue or due in the next 30 days.

Months for recorded times use the browser's time zone; stated dates are
calendar dates and never shift.

## Acceptance checks

- Two accounts never see each other's totals or events.
- Superseded receipt detail revisions, cleared totals, unconfirmed receipts,
  skipped lines and erased sources do not count.
- Multiple currencies stay separate; undated totals are reported, not bucketed.
- Bounded queries; a page that hits a bound says it is truncated.
- UI: light and dark themes, phone width, keyboard access, empty and error states.

## API

- `GET /api/insights/dashboard?months=6|12|24&timezone=<IANA zone>`: month
  labels, `spending` per currency (`total_minor`, `by_month`, `undated_minor`,
  `undated_count`, `largest`), `missing_total_count`, `activity` counts per
  month, `overdue_count`, `upcoming` maintenance and `truncated`.
- `GET /api/insights/timeline?month=YYYY-MM&kind=<kind>&timezone=<zone>`:
  `items` with `kind`, `date`, `date_basis` (`stated` or `recorded`), `title`,
  `detail`, optional amount and a `target` page and id. Kinds: `purchase`,
  `order`, `maintenance_done`, `maintenance_due`, `asset`, `document`, `photo`.
- `GET /api/insights/overview?timezone=<zone>` (v0.105.0, for the Overview
  page): `counts` of assets, documents, photos and memories (saved sources),
  `review_count` (the Review queue's pending items), `overdue_count`,
  `upcoming` maintenance as above, `today`, and the six newest assets,
  documents and photos in `recent` with `recorded_at` and a `target`.

The logic lives in `lifegather/insights/service.py`; the routes are thin
authenticated read adapters. No MCP tool yet: the assistant can already read
receipts, purchases and maintenance through its existing tools.
