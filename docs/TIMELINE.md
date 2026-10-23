# Timeline and dashboards

Status: in progress on branch `claude/timelines-and-dashboards` (2026-10-23).
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
