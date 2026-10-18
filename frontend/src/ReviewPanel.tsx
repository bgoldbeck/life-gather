import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ReceiptProposalCard } from './ReceiptProposalCard'
import { AssetProposalCard } from './AssetProposalCard'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ChatRequestError } from './chatRequest'

type Item = {
  key: string
  kind: 'proposal' | 'identity' | 'receipt'
  id: string
  name: string
  reason: string
  source_id: string
}
type Identity = {
  observation_id: string
  decision_id: string
  outcome: string
  reason: string
  observation: {
    name: string
    quote: string
    source_id: string
    quantity: number
    kind: string
    manufacturer: string | null
    model: string | null
    serial: string | null
  }
  candidates: { id: string; name: string }[]
  reliable_ids: string[]
}

export function ReviewPanel({ csrfToken }: { csrfToken: string }) {
  const [items, setItems] = useState<Item[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [kind, setKind] = useState('all')
  const [selected, setSelected] = useState<Item | null>(null)
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [source, setSource] = useState<EvidenceSource | null>(null)
  const [busy, setBusy] = useState(true)
  const [retry, setRetry] = useState(false)
  const [choice, setChoice] = useState('')
  const [targets, setTargets] = useState<string[]>([])
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const pending = useRef<Record<string, unknown> | null>(null)
  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch('/api/' + path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (!response.ok)
        throw new ChatRequestError(
          'Unable to complete this review. Reload to check whether it changed.',
          response.status,
        )
      return response.json()
    },
    [csrfToken],
  )
  const chatRequest = useCallback(
    (path: string, init?: RequestInit) => request('chat' + path, init),
    [request],
  )
  const load = useCallback(
    async (next = '') => {
      const page = await request(
        `reviews?kind=${kind}&cursor=${encodeURIComponent(next)}`,
      )
      setItems((current) => (next ? [...current, ...page.items] : page.items))
      setCursor(page.next_cursor)
    },
    [kind, request],
  )
  useEffect(() => {
    const controller = new AbortController()
    void request(`reviews?kind=${kind}`, { signal: controller.signal })
      .then((page) => {
        if (!controller.signal.aborted) {
          setItems(page.items)
          setCursor(page.next_cursor)
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load the review queue. Use Refresh to try again.')
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false)
      })
    return () => controller.abort()
  }, [kind, request])
  async function open(item: Item) {
    setBusy(true)
    setError('')
    setStatus('')
    setSource(null)
    setIdentity(null)
    setSelected(null)
    setChoice('')
    setTargets([])
    try {
      if (item.kind === 'identity')
        setIdentity(await request('reviews/identities/' + item.id))
      setSelected(item)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  async function openSource(id: string) {
    try {
      setSource(await chatRequest('/sources/' + id))
    } catch (caught) {
      setError((caught as Error).message)
    }
  }
  async function reviewed() {
    await load()
    setStatus('Review saved. The queue now reflects the current records.')
  }
  async function decide() {
    if (!identity || busy || (!choice && !pending.current)) return
    setBusy(true)
    setError('')
    const body = pending.current ?? {
      observation_id: identity.observation_id,
      expected_decision_id: identity.decision_id,
      action: choice,
      asset_ids: choice === 'link' ? targets : [],
      candidate_ids: identity.candidates.map((c) => c.id),
    }
    pending.current = body
    try {
      await request('reviews/identities/review', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      pending.current = null
      setRetry(false)
      setIdentity(null)
      setSelected(null)
      setSource(null)
      await reviewed()
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
  async function refresh(next = '') {
    setBusy(true)
    setError('')
    try {
      await load(next)
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const canResolve =
    identity && ['purchase', 'possession'].includes(identity.observation.kind)
  const completeTargets =
    identity &&
    targets.filter(Boolean).length === identity.observation.quantity &&
    new Set(targets).size === targets.length
  return (
    <section className="assets-panel" aria-label="Review queue">
      <h1>Review queue</h1>
      <p>
        Unfinished item proposals and uncertain identity matches stay here until
        you decide. No AI request is needed to review them.
      </p>
      <label>
        Review type
        <select
          value={kind}
          disabled={busy || retry}
          onChange={(e) => {
            setKind(e.target.value)
            setBusy(true)
            setError('')
            setSelected(null)
            setIdentity(null)
            setSource(null)
          }}
        >
          <option value="all">All pending</option>
          <option value="proposals">Item proposals</option>
          <option value="receipts">Multi-item receipts</option>
          <option value="identities">Identity matches</option>
        </select>
      </label>
      <Button
        variant="outline"
        disabled={busy || retry}
        onClick={() => void refresh()}
      >
        Refresh queue
      </Button>
      {busy && <p role="status">Loading review…</p>}
      {error && <p role="alert">{error}</p>}
      {status && <p role="status">{status}</p>}
      {!busy && !items.length && !error && (
        <p>No pending reviews in this view.</p>
      )}
      <ul className="asset-list">
        {items.map((item) => (
          <li key={item.key}>
            <div>
              <strong>
                {item.kind === 'receipt'
                  ? 'Multi-item receipt'
                  : item.kind === 'proposal'
                    ? 'Item proposal'
                    : 'Identity match'}
              </strong>
              <p>{item.reason}</p>
            </div>
            <Button
              disabled={busy || retry}
              variant="outline"
              onClick={() => void open(item)}
            >
              {item.name}
            </Button>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button disabled={busy || retry} onClick={() => void refresh(cursor)}>
          More reviews
        </Button>
      )}
      {selected && (
        <div className="asset-detail">
          <Button
            variant="outline"
            disabled={busy || retry}
            onClick={() => {
              setSelected(null)
              setIdentity(null)
              setSource(null)
              setStatus('Left pending. You can return to this review later.')
            }}
          >
            Not sure — leave pending
          </Button>
          {selected.kind === 'receipt' && (
            <ReceiptProposalCard
              key={selected.id}
              id={selected.id}
              csrfToken={csrfToken}
              onOpen={openSource}
              onReviewed={reviewed}
            />
          )}
          {selected.kind === 'proposal' && (
            <AssetProposalCard
              key={selected.id}
              id={selected.id}
              request={chatRequest}
              onOpen={openSource}
              onReviewed={reviewed}
            />
          )}
          {identity && (
            <section aria-label="Identity review">
              <h2>{identity.observation.name}</h2>
              <p>{identity.reason}</p>
              <p>
                {identity.observation.quantity} physical unit(s) ·{' '}
                {identity.observation.kind}. Ownership remains inferred.
              </p>
              <p>
                Manufacturer: {identity.observation.manufacturer ?? 'Unknown'} ·
                Model: {identity.observation.model ?? 'Unknown'} · Serial:{' '}
                {identity.observation.serial ?? 'Unknown'}
              </p>
              <blockquote>{identity.observation.quote}</blockquote>
              <Button
                variant="outline"
                onClick={() => void openSource(identity.observation.source_id)}
              >
                View original source
              </Button>
              {identity.outcome !== 'review' ? (
                <p>
                  This match has already been reviewed. Refresh the queue to see
                  current work.
                </p>
              ) : (
                <>
                  {!canResolve && (
                    <p>
                      A mention or payment does not establish possession. Save a
                      possession note before adding inventory.
                    </p>
                  )}
                  <fieldset disabled={busy || retry}>
                    <legend>
                      How should these physical items be recorded?
                    </legend>
                    {canResolve && (
                      <>
                        <label>
                          <input
                            type="radio"
                            name="identity-choice"
                            value="new"
                            checked={choice === 'new'}
                            disabled={identity.reliable_ids.length > 0}
                            onChange={() => setChoice('new')}
                          />
                          Different items — create{' '}
                          {identity.observation.quantity} new physical item(s)
                        </label>
                        {!!identity.reliable_ids.length && (
                          <p>
                            An identifier matches an existing item. Review the
                            matching item before continuing.
                          </p>
                        )}
                        {!!identity.candidates.length && (
                          <>
                            <label>
                              <input
                                type="radio"
                                name="identity-choice"
                                value="link"
                                checked={choice === 'link'}
                                onChange={() => {
                                  setChoice('link')
                                  setTargets(
                                    Array(identity.observation.quantity).fill(
                                      '',
                                    ),
                                  )
                                }}
                              />
                              Same items — choose existing records for every
                              unit
                            </label>
                            {choice === 'link' &&
                              Array.from(
                                { length: identity.observation.quantity },
                                (_, unit) => (
                                  <label key={unit}>
                                    Existing item for unit {unit + 1}
                                    <select
                                      value={targets[unit] ?? ''}
                                      onChange={(e) =>
                                        setTargets((current) =>
                                          current.map((v, i) =>
                                            i === unit ? e.target.value : v,
                                          ),
                                        )
                                      }
                                    >
                                      <option value="">
                                        Choose a distinct item
                                      </option>
                                      {identity.candidates.map((candidate) => (
                                        <option
                                          key={candidate.id}
                                          value={candidate.id}
                                        >
                                          {candidate.name} ·{' '}
                                          {candidate.id.slice(0, 8)}
                                        </option>
                                      ))}
                                    </select>
                                  </label>
                                ),
                              )}
                          </>
                        )}
                      </>
                    )}
                    <label>
                      <input
                        type="radio"
                        name="identity-choice"
                        value="dismiss"
                        checked={choice === 'dismiss'}
                        onChange={() => setChoice('dismiss')}
                      />
                      Exclude this discovery from inventory; preserve its source
                      and history
                    </label>
                  </fieldset>
                  <p>
                    Name similarity alone does not establish identity.
                    Multi-unit reviews require all-new items or a distinct
                    existing record for every unit.
                  </p>
                  <Button
                    disabled={
                      busy ||
                      (!retry &&
                        (!choice || (choice === 'link' && !completeTargets)))
                    }
                    onClick={() => void decide()}
                  >
                    {retry ? 'Retry same review' : 'Confirm identity review'}
                  </Button>
                </>
              )}
            </section>
          )}
        </div>
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={null}
          opening={busy}
          onOpen={openSource}
          onClose={() => setSource(null)}
          request={chatRequest}
        />
      )}
    </section>
  )
}
