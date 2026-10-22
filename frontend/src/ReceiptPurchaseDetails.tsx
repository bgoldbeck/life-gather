import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ChatRequestError } from './chatRequest'
import { ReceiptDetailSuggestions } from './ReceiptDetailSuggestions'
type Revision = {
  id: string
  revision: number
  line_total: string | null
  total_minor: number | null
  currency: string | null
  purchase_date: string | null
  money_quote: string | null
  date_quote: string | null
  reason: string
  basis?: 'labeled' | 'reviewed'
  recorded_at: number
}
type Page = {
  current_head: string | null
  current: Revision | null
  can_edit: boolean
  items: Revision[]
  next_revision: number | null
  quantity: number
  suggestions?: {
    currency?: string | null
    line_total: string | null
    money_quote: string | null
    purchase_date: string | null
    date_quote: string | null
  } | null
}
export function ReceiptPurchaseDetails({
  id,
  index,
  csrfToken,
}: {
  id: string
  index: number
  csrfToken: string
}) {
  const [page, setPage] = useState<Page | null>(null)
  const [total, setTotal] = useState('')
  const [currency, setCurrency] = useState('USD')
  const [moneyQuote, setMoneyQuote] = useState('')
  const [date, setDate] = useState('')
  const [dateQuote, setDateQuote] = useState('')
  const [reason, setReason] = useState('')
  const [reviewed, setReviewed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const pending = useRef<Record<string, unknown> | null>(null)
  const request = useCallback(
    async (path: string, body: unknown, signal?: AbortSignal) => {
      const response = await fetch('/api/receipts/details/' + path, {
        method: 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        signal,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(body),
      })
      if (!response.ok)
        throw new ChatRequestError(
          'Unable to save purchase details. Use exact source passages that print the total and date; reload if this note or its details changed.',
          response.status,
        )
      return response.json()
    },
    [csrfToken],
  )
  const apply = useCallback((row: Page) => {
    setPage(row)
    setTotal(row.current?.line_total ?? '')
    setCurrency(row.current?.currency ?? 'USD')
    setMoneyQuote(row.current?.money_quote ?? '')
    setDate(row.current?.purchase_date ?? '')
    setDateQuote(row.current?.date_quote ?? '')
    setReason('')
    setReviewed(false)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    void request('read', { receipt_id: id, index }, controller.signal)
      .then((row) => {
        if (!controller.signal.aborted) apply(row)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load purchase details. Reload to try again.')
      })
    return () => controller.abort()
  }, [id, index, request, apply])
  async function load(older = false) {
    setBusy(true)
    setError('')
    try {
      const row: Page = await request('read', {
        receipt_id: id,
        index,
        before_revision: older ? (page?.next_revision ?? 0) : 0,
      })
      if (older)
        setPage((current) =>
          current
            ? {
                ...current,
                items: [...current.items, ...row.items],
                next_revision: row.next_revision,
              }
            : row,
        )
      else apply(row)
    } catch {
      setError('Unable to load purchase details. Try reloading.')
    } finally {
      setBusy(false)
    }
  }
  async function save() {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    const body = pending.current ?? {
      receipt_id: id,
      index,
      expected_head: page?.current_head ?? null,
      request_id: crypto.randomUUID(),
      line_total: total || null,
      currency,
      money_quote: moneyQuote || null,
      purchase_date: date || null,
      date_quote: dateQuote || null,
      reason,
      basis: reviewed ? 'reviewed' : 'labeled',
    }
    pending.current = body
    try {
      const row: Revision = await request('save', body)
      pending.current = null
      setRetry(false)
      apply({
        current_head: row.id,
        current: row,
        can_edit: page?.can_edit ?? false,
        quantity: page?.quantity ?? 0,
        items: [
          row,
          ...(page?.items ?? []).filter((item) => item.id !== row.id),
        ],
        next_revision: page?.next_revision ?? null,
        suggestions: page?.suggestions,
      })
      setNotice(
        'Purchase details saved with source evidence. Earlier revisions are preserved.',
      )
    } catch (caught) {
      if (caught instanceof ChatRequestError && caught.status < 500) {
        pending.current = null
        setRetry(false)
      } else setRetry(true)
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const locked = busy || retry || !page?.can_edit
  return (
    <section
      className="receipt-purchase-details"
      aria-label={`Purchase details for item ${index + 1}`}
    >
      <h3>Purchase details for item {index + 1}</h3>
      <p>
        Optional source claims, not verified accounting. The line total covers
        all {page?.quantity ?? 'selected'} units together; it is never
        multiplied by quantity. Explicit USD/EUR/GBP/CAD/AUD/JPY totals and
        YYYY-MM-DD purchase dates are supported. JPY uses whole yen; the others
        use two decimal places. Printed values such as $349.00 or 10/18/2026 can
        be saved once you confirm their currency and date reading, for example
        from an AI suggestion. No currency conversion is performed. Leave
        unknown values blank.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <Button
        variant="outline"
        disabled={busy || retry}
        onClick={() => void load()}
      >
        Reload purchase details
      </Button>
      {page && !page.can_edit && (
        <p>
          The original source changed or was deleted. These historical details
          remain readable; new details require a current receipt source.
        </p>
      )}
      {page && (
        <>
          {page.suggestions &&
            (page.suggestions.line_total || page.suggestions.purchase_date) && (
              <>
                <p>
                  Source suggestions are unverified. Review the draft before
                  saving; using them replaces the draft fields.
                </p>
                <Button
                  variant="outline"
                  disabled={locked}
                  onClick={() => {
                    const suggested = page.suggestions!
                    setTotal(suggested.line_total ?? '')
                    setCurrency(suggested.currency ?? 'USD')
                    setMoneyQuote(suggested.money_quote ?? '')
                    setDate(suggested.purchase_date ?? '')
                    setDateQuote(suggested.date_quote ?? '')
                    setReason('Reviewed source suggestions')
                    setReviewed(false)
                    setNotice(
                      'Suggestions copied into the draft. Nothing has been saved.',
                    )
                  }}
                >
                  Use source suggestions
                </Button>
              </>
            )}
          <ReceiptDetailSuggestions
            id={id}
            index={index}
            csrfToken={csrfToken}
            disabled={locked}
            onUse={(suggested) => {
              setTotal(suggested.line_total ?? '')
              setCurrency(suggested.currency ?? '')
              setMoneyQuote(suggested.money_quote ?? '')
              setDate(suggested.purchase_date ?? '')
              setDateQuote(suggested.date_quote ?? '')
              setReason('Checked AI suggestion against the receipt')
              setReviewed(true)
              setNotice(
                'AI suggestion copied into the draft. Check the currency and date reading, then save. Nothing has been saved.',
              )
            }}
          />
          <fieldset disabled={locked}>
            <label>
              Currency
              <select
                aria-label={`Currency ${index + 1}`}
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
              >
                {!currency && <option value="">Choose currency</option>}
                {['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'JPY'].map((code) => (
                  <option key={code} value={code}>
                    {code}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {currency || 'Unknown currency'} line total
              <input
                aria-label={`${currency || 'Unknown currency'} line total ${index + 1}`}
                value={total}
                inputMode="decimal"
                maxLength={14}
                placeholder={currency === 'JPY' ? '4990' : '49.90'}
                onChange={(e) => setTotal(e.target.value)}
              />
            </label>
            <label>
              Exact item and line-total passage
              <textarea
                aria-label={`Line-total passage ${index + 1}`}
                value={moneyQuote}
                maxLength={500}
                placeholder={`Copy the reviewed item quote and Line total: ${currency} ${currency === 'JPY' ? '4990' : '49.90'}`}
                onChange={(e) => setMoneyQuote(e.target.value)}
              />
            </label>
            <label>
              Purchase date
              <input
                aria-label={`Purchase date ${index + 1}`}
                value={date}
                maxLength={10}
                placeholder="YYYY-MM-DD"
                onChange={(e) => setDate(e.target.value)}
              />
            </label>
            <label>
              Exact purchase-date passage
              <input
                aria-label={`Purchase-date passage ${index + 1}`}
                value={dateQuote}
                maxLength={200}
                placeholder="Purchase date: 2026-10-18"
                onChange={(e) => setDateQuote(e.target.value)}
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
              />{' '}
              I checked the currency and date reading of the printed values
              (allows passages such as $349.00 or 10/18/2026 instead of labeled
              ones)
            </label>
            <label>
              Reason for this revision
              <input
                aria-label={`Revision reason ${index + 1}`}
                value={reason}
                maxLength={300}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
          </fieldset>
          <Button
            disabled={
              busy ||
              !page.can_edit ||
              (!retry && (!reason.trim() || (!!total && !currency)))
            }
            onClick={() => void save()}
          >
            {retry ? 'Retry same purchase details' : 'Save purchase details'}
          </Button>
          {retry && (
            <p>
              The response was lost. Fields are frozen so you can safely retry
              the same revision.
            </p>
          )}
          <h4>Recorded history</h4>
          {!page.items.length && <p>No purchase total or date recorded.</p>}
          <ol>
            {page.items.map((item) => (
              <li key={item.id}>
                <p>
                  Revision {item.revision} ·{' '}
                  {new Date(item.recorded_at / 1000).toLocaleString()}
                </p>
                <p>
                  Line total:{' '}
                  {item.line_total === null
                    ? 'unknown'
                    : `${item.currency} ${item.line_total}`}{' '}
                  · Purchase date: {item.purchase_date ?? 'unknown'}
                  {item.basis === 'reviewed' && ' · reviewed reading'}
                </p>
                {item.money_quote && (
                  <blockquote>{item.money_quote}</blockquote>
                )}
                {item.date_quote && <blockquote>{item.date_quote}</blockquote>}
                <p>{item.reason}</p>
              </li>
            ))}
          </ol>
          {page.next_revision && (
            <Button
              variant="outline"
              disabled={busy || retry}
              onClick={() => void load(true)}
            >
              Earlier purchase revisions
            </Button>
          )}
        </>
      )}
    </section>
  )
}
