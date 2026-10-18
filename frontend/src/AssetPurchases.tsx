import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ReceiptProposalCard } from './ReceiptProposalCard'
type Purchase = {
  key: string
  receipt_id: string
  index: number
  source_id: string
  name: string
  quantity: number
  unit: number
  source_current: boolean
  claim: null | {
    id: string
    revision: number
    line_total: string | null
    currency: string | null
    purchase_date: string | null
    money_quote: string | null
    date_quote: string | null
    recorded_at: number
  }
}
type Page = { items: Purchase[]; next_cursor: string | null }
export function AssetPurchases({
  assetId,
  csrfToken,
  onOpen,
}: {
  assetId: string
  csrfToken: string
  onOpen: (id: string) => Promise<void>
}) {
  const [page, setPage] = useState<Page | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [receipt, setReceipt] = useState('')
  const request = useCallback(
    async (cursor = '', signal?: AbortSignal) => {
      const response = await fetch(
        `/api/assets/${encodeURIComponent(assetId)}/purchases?cursor=${encodeURIComponent(cursor)}`,
        { credentials: 'same-origin', cache: 'no-store', signal },
      )
      if (!response.ok)
        throw new Error('Unable to load purchase records. Try refreshing.')
      return response.json() as Promise<Page>
    },
    [assetId],
  )
  useEffect(() => {
    const controller = new AbortController()
    void request('', controller.signal)
      .then((row) => {
        if (!controller.signal.aborted) setPage(row)
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setError((caught as Error).message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false)
      })
    return () => controller.abort()
  }, [request])
  async function load(more = false) {
    setBusy(true)
    setError('')
    try {
      const row = await request(more ? (page?.next_cursor ?? '') : '')
      setPage((current) =>
        more && current
          ? { ...row, items: [...current.items, ...row.items] }
          : row,
      )
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section aria-label="Asset purchase records" className="asset-purchases">
      <h3>Purchase records</h3>
      <p>
        Receipt lines currently associated with this physical item. Totals cover
        the whole receipt line across all its units, not this item's individual
        price. Separate receipts are not combined or added together.
      </p>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Loading purchase records…</p>}
      <Button variant="outline" disabled={busy} onClick={() => void load()}>
        Refresh purchase records
      </Button>
      {page && !page.items?.length && !busy && (
        <p>
          No purchased receipt lines are currently linked to this item. Other
          evidence may still appear below.
        </p>
      )}
      <ul>
        {page?.items?.map((item) => (
          <li key={item.key}>
            <h4>
              {item.name} · receipt line {item.index + 1}
            </h4>
            <p>
              This item is unit {item.unit} of {item.quantity}. The receipt
              supports a past purchase, not verified current ownership.
            </p>
            <p>
              Line total:{' '}
              {item.claim?.line_total != null
                ? `${item.claim.currency} ${item.claim.line_total}`
                : 'unknown'}{' '}
              · Purchase date: {item.claim?.purchase_date ?? 'unknown'}
            </p>
            {!item.source_current && (
              <p>
                Historical source: this note changed or its original file was
                deleted. Do not treat these claims as current verified facts.
              </p>
            )}
            {item.claim &&
              item.claim.line_total === null &&
              item.claim.purchase_date === null && (
                <p>
                  These optional purchase details were withdrawn to unknown.
                </p>
              )}
            {item.claim ? (
              <p>
                Latest recorded revision {item.claim.revision} ·{' '}
                {new Date(item.claim.recorded_at / 1000).toLocaleString()}.
                Earlier revisions remain in the receipt review.
              </p>
            ) : (
              <p>No optional purchase details have been recorded.</p>
            )}
            {item.claim?.money_quote && (
              <blockquote>{item.claim.money_quote}</blockquote>
            )}
            {item.claim?.date_quote && (
              <blockquote>{item.claim.date_quote}</blockquote>
            )}
            <Button
              variant="outline"
              onClick={() => void onOpen(item.source_id)}
            >
              View purchase source
            </Button>
            <Button
              variant="outline"
              onClick={() => setReceipt(item.receipt_id)}
            >
              Open receipt and purchase history
            </Button>
          </li>
        ))}
      </ul>
      {page?.next_cursor && (
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => void load(true)}
        >
          More purchase records
        </Button>
      )}
      {receipt && (
        <>
          <Button variant="outline" onClick={() => setReceipt('')}>
            Close purchase history
          </Button>
          <p>
            After editing purchase details, refresh purchase records above to
            update the summary.
          </p>
          <ReceiptProposalCard
            key={receipt}
            id={receipt}
            csrfToken={csrfToken}
            onOpen={onOpen}
          />
        </>
      )}
    </section>
  )
}
