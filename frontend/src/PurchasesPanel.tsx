import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { PurchaseEvidenceEditor } from './PurchaseEvidenceEditor'
import { PurchaseSourcePicker } from './PurchaseSourcePicker'
import { amountText, type Group, type Purchase } from './purchaseTypes'

export function PurchasesPanel({
  csrfToken,
  onOpenGraph,
}: {
  csrfToken: string
  onOpenGraph?: (id: string) => void
}) {
  const [items, setItems] = useState<Purchase[]>([])
  const [cursor, setCursor] = useState('')
  const [next, setNext] = useState<string | null>(null)
  const [selected, setSelected] = useState('')
  const [after, setAfter] = useState('')
  const [group, setGroup] = useState<Group | null>(null)
  const [source, setSource] = useState('')
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [locked, setLocked] = useState(false)
  const [loading, setLoading] = useState(true)
  const request = useCallback(
    async (path: string, init?: RequestInit): Promise<unknown> => {
      const response = await fetch('/api' + path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (!response.ok)
        throw new Error(
          'Unable to load or save purchase evidence. Check your session and refresh the current source.',
        )
      return response.json()
    },
    [csrfToken],
  )
  useEffect(() => {
    const controller = new AbortController()
    void request('/purchases?cursor=' + encodeURIComponent(cursor), {
      signal: controller.signal,
    })
      .then((value) => {
        if (controller.signal.aborted) return
        const page = value as { items: Purchase[]; next_cursor: string | null }
        setItems(page.items)
        setNext(page.next_cursor)
        setLoading(false)
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError('Unable to load purchases. Refresh purchases to retry.')
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [request, cursor, reload])
  useEffect(() => {
    if (!selected) return
    const controller = new AbortController()
    void request(
      '/purchases/' + selected + '?after=' + encodeURIComponent(after),
      { signal: controller.signal },
    )
      .then((value) => {
        if (!controller.signal.aborted) setGroup(value as Group)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            'Unable to load purchase evidence. Refresh purchases to retry.',
          )
      })
    return () => controller.abort()
  }, [request, selected, after, reload])
  function choose(id: string) {
    if (!locked) {
      setSource(id)
      setError('')
    }
  }
  function select(id: string) {
    setSelected(id)
    setAfter('')
    setGroup(null)
  }
  return (
    <section className="space-y-5">
      <h2 className="text-xl font-semibold">Purchases</h2>
      <p className="text-muted-foreground">
        Connect order confirmations, receipts, shipments and payments to one
        purchase. Review saved evidence explicitly; names, dates and matching
        amounts do not prove item identity. One current purchase association per
        saved source is supported here.
      </p>
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">Loading purchases…</p>}
      <Button
        variant="outline"
        onClick={() => {
          setError('')
          setReload((value) => value + 1)
        }}
      >
        Refresh purchases
      </Button>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id}>
            <Button variant="outline" onClick={() => select(item.id)}>
              {item.retailer} · {item.account_scope} · {item.order_id}
            </Button>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button variant="outline" onClick={() => setCursor('')}>
          First purchases
        </Button>
      )}
      {next && (
        <Button variant="outline" onClick={() => setCursor(next)}>
          More purchases
        </Button>
      )}
      {group && (
        <section
          className="space-y-3 rounded border p-4"
          aria-label="Purchase evidence"
        >
          <h3 className="font-semibold">
            {group.retailer} · {group.order_id}
          </h3>
          <p>
            Account: {group.account_scope} · {group.active_source_count} current
            source associations
          </p>
          {group.conflicting_totals && (
            <p role="status">
              Conflicting order totals: inspect the original claims. No total
              has been chosen.
            </p>
          )}
          <p>
            Amounts are separate source claims and are never summed. Shipments
            do not establish delivery or current ownership.
          </p>
          {group.items?.map((row) => (
            <article key={row.id} className="space-y-1 rounded border p-3">
              <p>
                {row.role} · revision {row.revision} · {row.currency}{' '}
                {amountText(row)}
              </p>
              <blockquote className="whitespace-pre-wrap">
                {row.quote}
              </blockquote>
              <p>{row.reason}</p>
              {!row.source_current && (
                <p>
                  Historical or unavailable source — excluded from current total
                  comparison.
                </p>
              )}
              <Button
                variant="outline"
                disabled={locked}
                onClick={() => choose(row.source_id)}
              >
                Inspect or correct this evidence
              </Button>
            </article>
          ))}
          {after && (
            <Button variant="outline" onClick={() => setAfter('')}>
              First purchase evidence
            </Button>
          )}
          {group.next_after && (
            <Button
              variant="outline"
              onClick={() => setAfter(group.next_after!)}
            >
              More purchase evidence
            </Button>
          )}
          {onOpenGraph &&
            group.linked_asset_ids?.map((id) => (
              <Button
                key={id}
                variant="outline"
                onClick={() => onOpenGraph(id)}
              >
                View linked item {id.slice(0, 8)} in graph
              </Button>
            ))}
          {group.assets_truncated && <p>Showing the first 20 linked items.</p>}
        </section>
      )}
      <PurchaseSourcePicker
        request={request}
        onChoose={choose}
        disabled={locked}
      />
      {source && (
        <PurchaseEvidenceEditor
          key={source}
          request={request}
          sourceId={source}
          purchases={items}
          locked={locked}
          onLock={setLocked}
          onChoose={choose}
          onSaved={(id) => {
            select(id)
            setReload((value) => value + 1)
          }}
        />
      )}
    </section>
  )
}
