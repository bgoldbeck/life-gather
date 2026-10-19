import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import {
  amountText,
  type Claim,
  type History,
  type Purchase,
  type Request,
  type SourceContext,
} from './purchaseTypes'

type Draft = {
  target: string
  retailer: string
  account: string
  order: string
  role: Claim['role']
  quote: string
  amount: string
  currency: string
  moneyQuote: string
  occurredOn: string
  dateQuote: string
  reason: string
}
const empty = (): Draft => ({
  target: '',
  retailer: '',
  account: '',
  order: '',
  role: 'order',
  quote: '',
  amount: '',
  currency: 'USD',
  moneyQuote: '',
  occurredOn: '',
  dateQuote: '',
  reason: '',
})

export function PurchaseEvidenceEditor({
  request,
  sourceId,
  purchases,
  onSaved,
  onChoose,
  locked,
  onLock,
}: {
  request: Request
  sourceId: string
  purchases: Purchase[]
  onSaved: (id: string) => void
  onChoose: (id: string) => void
  locked: boolean
  onLock: (locked: boolean) => void
}) {
  const [context, setContext] = useState<SourceContext | null>(null)
  const [history, setHistory] = useState<History | null>(null)
  const [before, setBefore] = useState(0)
  const [draft, setDraft] = useState(empty)
  const [reload, setReload] = useState(0)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const lifecycle = useRef<AbortController | null>(null)
  const pending = useRef<{ path: string; body: unknown } | null>(null)
  const saving = useRef(false)
  useEffect(() => {
    const controller = new AbortController()
    lifecycle.current = controller
    void Promise.all([
      request('/purchases/sources/' + sourceId, { signal: controller.signal }),
      request('/purchases/sources/' + sourceId + '/history', {
        signal: controller.signal,
      }),
    ])
      .then(([source, versions]) => {
        if (controller.signal.aborted) return
        const next = source as SourceContext
        setContext(next)
        setHistory(versions as History)
        setBefore(0)
        const h = next.head
        setDraft(
          h
            ? {
                target: h.purchase_id,
                retailer: '',
                account: '',
                order: '',
                role: h.role,
                quote: h.quote,
                amount: amountText(h),
                currency: h.currency ?? 'USD',
                moneyQuote: h.money_quote ?? '',
                occurredOn: h.occurred_on ?? '',
                dateQuote: h.date_quote ?? '',
                reason: '',
              }
            : empty(),
        )
        setLoading(false)
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setError(
            'Unable to load evidence. Refresh the evidence view to retry.',
          )
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [request, sourceId, reload])
  async function act(event: FormEvent, withdraw = false) {
    event.preventDefault()
    if (!context || saving.current || !lifecycle.current) return
    if (!draft.reason.trim()) {
      setError('Explain the association or correction.')
      return
    }
    const controller = lifecycle.current
    if (!pending.current) {
      const common = {
        source_id: sourceId,
        expected_head: context.head?.id ?? null,
        reason: draft.reason,
        request_id: crypto.randomUUID(),
      }
      pending.current = withdraw
        ? { path: '/purchases/withdraw', body: common }
        : {
            path: '/purchases/evidence',
            body: {
              ...common,
              purchase_id: draft.target || null,
              retailer: draft.target ? null : draft.retailer,
              account_scope: draft.target ? null : draft.account,
              order_id: draft.target ? null : draft.order,
              role: draft.role,
              quote: draft.quote,
              amount: draft.amount || null,
              currency: draft.currency,
              money_quote: draft.moneyQuote || null,
              occurred_on: draft.occurredOn || null,
              date_quote: draft.dateQuote || null,
            },
          }
    }
    saving.current = true
    setIsSaving(true)
    onLock(true)
    setError('')
    setNotice('')
    try {
      const saved = (await request(pending.current.path, {
        method: 'POST',
        body: JSON.stringify(pending.current.body),
        signal: controller.signal,
      })) as Claim
      if (controller.signal.aborted) return
      pending.current = null
      setRetry(false)
      onLock(false)
      setNotice(
        'Evidence saved. Original sources and previous associations are retained.',
      )
      setLoading(true)
      setReload((value) => value + 1)
      onSaved(saved.purchase_id)
    } catch {
      if (!controller.signal.aborted) {
        setRetry(true)
        setError(
          'Save was not confirmed. Retry uses the identical request. Refresh after discarding if the evidence was edited elsewhere.',
        )
      }
    } finally {
      saving.current = false
      if (!controller.signal.aborted) setIsSaving(false)
    }
  }
  async function older() {
    if (!history?.next_revision || locked || !lifecycle.current) return
    const controller = lifecycle.current
    try {
      const page = (await request(
        `/purchases/sources/${sourceId}/history?before_revision=${history.next_revision}`,
        { signal: controller.signal },
      )) as History
      if (!controller.signal.aborted) {
        setBefore(history.next_revision)
        setHistory(page)
      }
    } catch {
      if (!controller.signal.aborted)
        setError('Unable to load older evidence history.')
    }
  }
  return (
    <section
      className="space-y-3 rounded-xl border p-4"
      aria-label="Purchase evidence review"
    >
      <h3 className="font-semibold">Review purchase evidence</h3>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {loading && <p role="status">Loading source evidence…</p>}
      {!locked && (
        <Button
          variant="outline"
          onClick={() => {
            setLoading(true)
            setError('')
            setReload((value) => value + 1)
          }}
        >
          Refresh evidence view
        </Button>
      )}
      {!loading && context && (
        <>
          <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded border p-3 text-sm">
            {context.text}
          </pre>
          {!context.can_attach && (
            <p>
              This source is historical or its original was deleted. New
              associations require current available evidence; you may still
              withdraw the existing link.
            </p>
          )}
          {context.current_source_id !== sourceId && (
            <Button
              variant="outline"
              disabled={locked}
              onClick={() => onChoose(context.current_source_id)}
            >
              Open current source
            </Button>
          )}
          <form onSubmit={(event) => void act(event)} className="space-y-3">
            <fieldset disabled={locked} className="grid gap-3 sm:grid-cols-2">
              <label>
                Purchase target
                <select
                  value={draft.target}
                  onChange={(event) =>
                    setDraft({ ...draft, target: event.target.value })
                  }
                  className="block w-full rounded border bg-background p-2"
                >
                  <option value="">
                    Resolve by retailer/account/order reference
                  </option>
                  {draft.target &&
                    !purchases.some((p) => p.id === draft.target) && (
                      <option value={draft.target}>
                        Current linked purchase · {draft.target.slice(0, 8)}
                      </option>
                    )}
                  {purchases.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.retailer} · {p.account_scope} · {p.order_id}
                    </option>
                  ))}
                </select>
              </label>
              {!draft.target && (
                <>
                  <label>
                    Retailer
                    <input
                      required
                      maxLength={100}
                      value={draft.retailer}
                      onChange={(event) =>
                        setDraft({ ...draft, retailer: event.target.value })
                      }
                      className="block w-full rounded border bg-background p-2"
                    />
                  </label>
                  <label>
                    Private account label
                    <input
                      required
                      maxLength={100}
                      value={draft.account}
                      onChange={(event) =>
                        setDraft({ ...draft, account: event.target.value })
                      }
                      className="block w-full rounded border bg-background p-2"
                    />
                  </label>
                  <label>
                    Order ID
                    <input
                      required
                      maxLength={100}
                      value={draft.order}
                      onChange={(event) =>
                        setDraft({ ...draft, order: event.target.value })
                      }
                      className="block w-full rounded border bg-background p-2"
                    />
                  </label>
                </>
              )}
              <label>
                Evidence role
                <select
                  value={draft.role}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      role: event.target.value as Claim['role'],
                      amount: '',
                      moneyQuote: '',
                    })
                  }
                  className="block rounded border bg-background p-2"
                >
                  {['order', 'receipt', 'shipment', 'payment'].map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </label>
              <label className="sm:col-span-2">
                Exact evidence quote
                <textarea
                  required
                  maxLength={2000}
                  value={draft.quote}
                  onChange={(event) =>
                    setDraft({ ...draft, quote: event.target.value })
                  }
                  className="block min-h-24 w-full rounded border bg-background p-2"
                />
              </label>
              {draft.role !== 'shipment' && (
                <>
                  <label>
                    {draft.role === 'payment'
                      ? 'Payment amount (optional)'
                      : 'Order total (optional)'}
                    <input
                      inputMode="decimal"
                      maxLength={14}
                      value={draft.amount}
                      onChange={(event) =>
                        setDraft({ ...draft, amount: event.target.value })
                      }
                      className="block rounded border bg-background p-2"
                    />
                  </label>
                  <label>
                    Currency
                    <select
                      value={draft.currency}
                      onChange={(event) =>
                        setDraft({ ...draft, currency: event.target.value })
                      }
                      className="block rounded border bg-background p-2"
                    >
                      {['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY'].map(
                        (code) => (
                          <option key={code}>{code}</option>
                        ),
                      )}
                    </select>
                  </label>
                  <label>
                    Exact amount quote
                    <input
                      maxLength={500}
                      value={draft.moneyQuote}
                      onChange={(event) =>
                        setDraft({ ...draft, moneyQuote: event.target.value })
                      }
                      placeholder="USD 349.00"
                      className="block w-full rounded border bg-background p-2"
                    />
                  </label>
                </>
              )}
              <label>
                Event date (optional)
                <input
                  type="date"
                  value={draft.occurredOn}
                  onChange={(event) =>
                    setDraft({ ...draft, occurredOn: event.target.value })
                  }
                  className="block rounded border bg-background p-2"
                />
              </label>
              <label>
                Exact event date quote
                <input
                  maxLength={200}
                  value={draft.dateQuote}
                  onChange={(event) =>
                    setDraft({ ...draft, dateQuote: event.target.value })
                  }
                  className="block w-full rounded border bg-background p-2"
                />
              </label>
              <label className="sm:col-span-2">
                Association or correction reason
                <textarea
                  required
                  maxLength={300}
                  value={draft.reason}
                  onChange={(event) =>
                    setDraft({ ...draft, reason: event.target.value })
                  }
                  className="block w-full rounded border bg-background p-2"
                />
              </label>
            </fieldset>
            <p className="text-sm text-muted-foreground">
              Retailer/order IDs must occur in the exact quote. Account labels
              distinguish your retailer accounts. Payment-only evidence needs an
              existing purchase. Amounts need one currency-coded passage inside
              the evidence quote and are never added together. This does not
              create assets or change ownership.
            </p>
            <Button
              type="submit"
              disabled={isSaving || (!retry && !context.can_attach)}
            >
              {retry ? 'Retry evidence request' : 'Save purchase evidence'}
            </Button>
            {!retry && context.head?.state === 'active' && (
              <Button
                type="button"
                variant="outline"
                disabled={locked}
                onClick={(event) => void act(event, true)}
              >
                Withdraw selected association
              </Button>
            )}
            {retry && (
              <Button
                type="button"
                variant="outline"
                disabled={isSaving}
                onClick={() => {
                  pending.current = null
                  setRetry(false)
                  onLock(false)
                  setError('')
                  setNotice(
                    'Request draft discarded. Refresh before editing if a response was lost.',
                  )
                }}
              >
                Discard evidence request
              </Button>
            )}
          </form>
          <h4 className="font-semibold">Association history</h4>
          {history?.items.map((row) => (
            <article key={row.id} className="rounded border p-3 text-sm">
              <p>
                Revision {row.revision} · {row.state} · {row.role} · purchase{' '}
                {row.purchase_id.slice(0, 8)}{' '}
                {row.superseded_at ? '· Superseded' : ''}
              </p>
              <p>{row.reason}</p>
              <p>
                {row.occurred_on ?? 'Event date unknown'} · Recorded{' '}
                {new Date(row.recorded_at / 1000).toLocaleString()}
              </p>
              <p>
                {row.currency} {amountText(row)}
              </p>
              <blockquote className="whitespace-pre-wrap">
                {row.quote}
              </blockquote>
              {!row.source_current && <p>Historical or unavailable source.</p>}
            </article>
          ))}
          {before > 0 && (
            <Button
              variant="outline"
              disabled={locked}
              onClick={() => {
                setLoading(true)
                setReload((value) => value + 1)
              }}
            >
              Newest association history
            </Button>
          )}
          {history?.next_revision && (
            <Button
              variant="outline"
              disabled={locked}
              onClick={() => void older()}
            >
              Older association history
            </Button>
          )}
        </>
      )}
    </section>
  )
}
