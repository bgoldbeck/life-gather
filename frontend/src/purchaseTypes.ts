export type Purchase = {
  id: string
  retailer: string
  account_scope: string
  order_id: string
}
export type Claim = {
  id: string
  purchase_id: string
  source_id: string
  root_source_id: string
  revision: number
  previous_id: string | null
  superseded_at: number | null
  state: 'active' | 'withdrawn'
  role: 'order' | 'receipt' | 'shipment' | 'payment'
  quote: string
  amount_minor: number | null
  currency: string | null
  money_quote: string | null
  occurred_on: string | null
  date_quote: string | null
  reason: string
  recorded_at: number
  source_current: boolean
}
export type Group = Purchase & {
  items: Claim[]
  next_after: string | null
  active_source_count: number
  conflicting_totals: boolean
  linked_asset_ids: string[]
  assets_truncated: boolean
}
export type SourceContext = {
  source_id: string
  root_source_id: string
  current_source_id: string
  text: string
  can_attach: boolean
  head: Claim | null
}
export type History = { items: Claim[]; next_revision: number | null }
export type Request = (path: string, init?: RequestInit) => Promise<unknown>
export function amountText(claim: Claim): string {
  if (claim.amount_minor === null) return ''
  return claim.currency === 'JPY'
    ? String(claim.amount_minor)
    : (claim.amount_minor / 100).toFixed(2)
}
