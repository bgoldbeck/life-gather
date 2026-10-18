import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import './assets.css'
import { PhotosPanel } from './PhotosPanel'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { ChatRequestError } from './chatRequest'
import { AssetActions } from './AssetActions'
import { AssetPurchases } from './AssetPurchases'

type Asset = {
  id: string
  name: string
  source_id: string
  recorded_at: number
  in_inventory?: boolean
}
type Decision = {
  id: string
  unit?: number
  quantity?: number
  name: string
  manufacturer: string | null
  model: string | null
  serial: string | null
  quote: string
  source_id: string
  outcome: string
  reason: string
  recorded_at: number
  superseded_at: number | null
}
type Fact = {
  id: string
  predicate: string
  value: unknown
  object_id: string | null
  object_name?: string | null
  status: string
  recorded_at: number
  valid_from: string | null
  valid_to: string | null
  superseded_at: number | null
  evidence: { source_id: string; quote?: string | null }[]
}
type Detail = {
  asset: Asset
  in_inventory: boolean
  decisions: Decision[]
  facts: Fact[]
  next_fact_cursor: string | null
  next_decision_cursor: string | null
  action_head?: string
  next_action_cursor?: string | null
  actions?: {
    id: string
    operation: string
    note: string
    source_id: string
    recorded_at: number
    direction?: string
    asset_name?: string
    target_asset_name?: string | null
  }[]
}
type Source = EvidenceSource & { next_offset: number | null }

const recorded = (stamp: number) => new Date(stamp / 1000).toLocaleString()

export function AssetsPanel({
  refreshSession,
  csrfToken = '',
  initialAssetId = '',
  onOpenGraph,
}: {
  refreshSession?: () => Promise<void>
  csrfToken?: string
  initialAssetId?: string
  onOpenGraph?: (id: string) => void
}) {
  const [items, setItems] = useState<Asset[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [history, setHistory] = useState(false)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [source, setSource] = useState<Source | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const selectedAsset = useRef('')
  const selectAsset = useCallback((id: string) => {
    selectedAsset.current = id
    return ++generation.current
  }, [])
  const request = useCallback(
    async (path: string, signal?: AbortSignal) => {
      const response = await fetch('/api/' + path, {
        credentials: 'same-origin',
        cache: 'no-store',
        signal,
      })
      if (response.status === 401) await refreshSession?.()
      if (!response.ok)
        throw new Error('Unable to load these records. Please try again.')
      return response.json()
    },
    [refreshSession],
  )

  useEffect(() => {
    const controller = new AbortController()
    selectAsset(initialAssetId)
    async function load() {
      setBusy(true)
      setError('')
      setDetail(null)
      setSource(null)
      try {
        const page = await request(
          `assets?query=${encodeURIComponent(search)}&include_history=${history}`,
          controller.signal,
        )
        if (!controller.signal.aborted) {
          setItems(page.items)
          setCursor(page.next_cursor)
          if (initialAssetId) {
            const row: Detail = await request(
              `assets/${encodeURIComponent(initialAssetId)}`,
              controller.signal,
            )
            if (!controller.signal.aborted) setDetail(row)
          }
        }
      } catch (caught) {
        if (!controller.signal.aborted) setError((caught as Error).message)
      } finally {
        if (!controller.signal.aborted) setBusy(false)
      }
    }
    void load()
    return () => {
      controller.abort()
      selectAsset('')
    }
  }, [request, search, history, initialAssetId, selectAsset])

  async function more() {
    const version = ++generation.current
    setBusy(true)
    setError('')
    try {
      const page = await request(
        `assets?query=${encodeURIComponent(search)}&include_history=${history}&cursor=${cursor}`,
      )
      if (version !== generation.current) return
      setItems((current) => [...current, ...page.items])
      setCursor(page.next_cursor)
    } catch (caught) {
      if (version === generation.current) setError((caught as Error).message)
    } finally {
      if (version === generation.current) setBusy(false)
    }
  }
  async function open(id: string, kind?: 'fact' | 'decision') {
    if (kind && selectedAsset.current !== id) return
    const version = selectAsset(id)
    setBusy(true)
    setError('')
    setSource(null)
    try {
      const next =
        kind === 'fact'
          ? detail?.next_fact_cursor
          : detail?.next_decision_cursor
      const row: Detail = await request(
        `assets/${id}${kind ? `?${kind}_cursor=${next}` : ''}`,
      )
      if (version !== generation.current) return
      setDetail((current) =>
        kind && current
          ? {
              ...row,
              facts:
                kind === 'fact'
                  ? [...current.facts, ...row.facts]
                  : current.facts,
              decisions:
                kind === 'decision'
                  ? [...current.decisions, ...row.decisions]
                  : current.decisions,
              next_fact_cursor:
                kind === 'fact'
                  ? row.next_fact_cursor
                  : current.next_fact_cursor,
              next_decision_cursor:
                kind === 'decision'
                  ? row.next_decision_cursor
                  : current.next_decision_cursor,
            }
          : row,
      )
    } catch (caught) {
      if (version === generation.current) setError((caught as Error).message)
    } finally {
      if (version === generation.current) setBusy(false)
    }
  }
  const chatRequest = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch('/api/chat' + path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (response.status === 401) await refreshSession?.()
      if (!response.ok)
        throw new ChatRequestError(
          'Unable to load or correct this source. Please try again.',
          response.status,
        )
      return response.json()
    },
    [csrfToken, refreshSession],
  )
  async function evidence(id: string, offset = 0) {
    const version = ++generation.current
    setBusy(true)
    setError('')
    try {
      const row = await request(`chat/sources/${id}?offset=${offset}`)
      if (version === generation.current) setSource(row)
    } catch (caught) {
      if (version === generation.current) setError((caught as Error).message)
    } finally {
      if (version === generation.current) setBusy(false)
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    setSearch(query)
  }

  async function refreshed() {
    if (!detail || selectedAsset.current !== detail.asset.id) return
    const version = ++generation.current
    try {
      const [row, page] = await Promise.all([
        request(`assets/${detail.asset.id}`),
        request(
          `assets?query=${encodeURIComponent(search)}&include_history=${history}`,
        ),
      ])
      if (version !== generation.current) return
      setDetail(row)
      setItems(page.items)
      setCursor(page.next_cursor)
    } finally {
      if (version === generation.current) setBusy(false)
    }
  }
  async function moreActions() {
    if (
      !detail?.next_action_cursor ||
      selectedAsset.current !== detail.asset.id
    )
      return
    const version = ++generation.current
    const id = detail.asset.id
    setBusy(true)
    setError('')
    try {
      const page: Detail = await request(
        `assets/${detail.asset.id}?action_cursor=${detail.next_action_cursor}`,
      )
      if (version !== generation.current) return
      setDetail((current) =>
        current && current.asset.id === id
          ? {
              ...current,
              actions: [...(current.actions ?? []), ...(page.actions ?? [])],
              next_action_cursor: page.next_action_cursor,
            }
          : current,
      )
    } catch (caught) {
      if (version === generation.current) setError((caught as Error).message)
    } finally {
      if (version === generation.current) setBusy(false)
    }
  }

  return (
    <section className="assets-panel" aria-label="Your assets">
      <h1>Assets</h1>
      <p>
        Find your items and follow their original evidence. Inventory and
        ownership may be inferred.
      </p>
      <form className="asset-search" onSubmit={submit}>
        <label>
          Search item names
          <input
            value={query}
            maxLength={200}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <Button disabled={busy} type="submit">
          Search assets
        </Button>
        <label>
          <input
            type="checkbox"
            checked={history}
            disabled={busy}
            onChange={(event) => setHistory(event.target.checked)}
          />
          Include historical records
        </label>
      </form>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Loading records…</p>}
      {!busy && !items.length && (
        <p>
          No assets found. Confirm a supported proposal in Chat to add an item.
        </p>
      )}
      <ul className="asset-list">
        {items.map((item) => (
          <li key={item.id}>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => void open(item.id)}
            >
              {item.name}
            </Button>
            <span>
              {item.in_inventory
                ? 'In inventory · source-backed ownership'
                : 'Historical record · not active inventory'}
            </span>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button disabled={busy} variant="outline" onClick={() => void more()}>
          More assets
        </Button>
      )}
      {detail && (
        <section className="asset-detail" aria-label="Asset details">
          <h2>{detail.asset.name}</h2>
          {onOpenGraph && (
            <Button
              variant="outline"
              onClick={() => onOpenGraph(detail.asset.id)}
            >
              View in graph
            </Button>
          )}
          <p>
            {detail.in_inventory
              ? 'In inventory. This does not independently verify current ownership.'
              : 'Historical item record. No active inventory claim.'}
          </p>
          <p>
            Recorded {recorded(detail.asset.recorded_at)}. Prices and world
            dates are unknown unless separately supported.
          </p>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void evidence(detail.asset.source_id)}
          >
            View original evidence
          </Button>
          <PhotosPanel
            key={detail.asset.id}
            assetId={detail.asset.id}
            csrfToken={csrfToken}
          />
          <AssetPurchases
            key={`${detail.asset.id}:${detail.action_head ?? ''}:${detail.decisions
              .filter((decision) => decision.superseded_at === null)
              .map((decision) => decision.id)
              .join(',')}`}
            assetId={detail.asset.id}
            csrfToken={csrfToken}
            onOpen={evidence}
          />
          <h3>Sourced details and decisions</h3>
          <details>
            <summary>Make a correction</summary>
            <AssetActions
              key={`${detail.asset.id}:${detail.action_head ?? ''}`}
              assetId={detail.asset.id}
              head={detail.action_head ?? ''}
              decisions={detail.decisions}
              csrfToken={csrfToken}
              onChanged={refreshed}
              onOpen={evidence}
              assetName={detail.asset.name}
            />
          </details>
          {!!detail.actions?.length && (
            <section aria-label="Correction history">
              <h3>Correction history</h3>
              {detail.actions.map((action) => (
                <article key={action.id}>
                  <p>
                    {action.direction === 'incoming'
                      ? `Evidence received from ${action.asset_name ?? 'another item'}`
                      : action.operation === 'reassociate' &&
                          action.target_asset_name
                        ? `Evidence moved to ${action.target_asset_name}`
                        : ((
                            {
                              ownership: 'Ownership statement',
                              undo: 'Decision undone',
                              reassociate: 'Evidence reassociated',
                            } as Record<string, string>
                          )[action.operation] ?? action.operation)}{' '}
                    · {recorded(action.recorded_at)}
                  </p>
                  <blockquote>{action.note}</blockquote>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void evidence(action.source_id)}
                  >
                    View correction evidence
                  </Button>
                </article>
              ))}
              {detail.next_action_cursor && (
                <Button disabled={busy} onClick={() => void moreActions()}>
                  More corrections
                </Button>
              )}
            </section>
          )}
          {!detail.decisions.length && (
            <p>No reconciliation decisions for this item.</p>
          )}
          {detail.decisions.map((decision) => (
            <article key={decision.id}>
              <p>
                {decision.superseded_at === null
                  ? 'Current evidence association'
                  : 'Earlier evidence association'}{' '}
                ·{' '}
                {(
                  {
                    create: 'Added item',
                    enrich: 'Linked evidence',
                    review: 'Awaiting review',
                    dismissed: 'Excluded',
                  } as Record<string, string>
                )[decision.outcome] ?? decision.outcome}{' '}
                · recorded {recorded(decision.recorded_at)}
              </p>
              <p>
                <span>Reason recorded then: </span>
                <span>{decision.reason}</span>
              </p>
              {(decision.quantity ?? 1) > 1 && (
                <p>
                  This item is unit {(decision.unit ?? 0) + 1} of{' '}
                  {decision.quantity} in this source line.
                </p>
              )}
              <dl>
                <dt>Manufacturer</dt>
                <dd>{decision.manufacturer ?? 'Unknown'}</dd>
                <dt>Model</dt>
                <dd>{decision.model ?? 'Unknown'}</dd>
                <dt>Serial</dt>
                <dd>{decision.serial ?? 'Unknown'}</dd>
              </dl>
              <blockquote>{decision.quote}</blockquote>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void evidence(decision.source_id)}
              >
                View decision evidence
              </Button>
            </article>
          ))}
          {detail.next_decision_cursor && (
            <Button
              disabled={busy}
              onClick={() => void open(detail.asset.id, 'decision')}
            >
              More decisions
            </Button>
          )}
          <h3>Facts and their history</h3>
          <p>
            Recorded time is when LifeGather saved a version; valid-world dates
            describe the statement's real-world interval. Sources can disagree;
            an earlier purchase inference does not establish ownership today.
          </p>
          {detail.facts.map((fact) => (
            <article key={fact.id}>
              <p>
                {fact.predicate.replaceAll('_', ' ')}:{' '}
                {fact.object_id
                  ? (fact.object_name ?? 'Linked item')
                  : JSON.stringify(fact.value)}{' '}
                · {fact.status} ·{' '}
                {fact.superseded_at === null
                  ? 'latest version of this statement'
                  : 'superseded version'}
              </p>
              <p>
                Recorded {recorded(fact.recorded_at)} · valid from{' '}
                {fact.valid_from ?? 'unknown'} to{' '}
                {fact.valid_to ?? 'unspecified'}
              </p>
              {fact.evidence.map((item, index) => (
                <div key={`${item.source_id}-${index}`}>
                  <blockquote>{item.quote}</blockquote>
                  <Button
                    disabled={busy}
                    variant="outline"
                    onClick={() => void evidence(item.source_id)}
                  >
                    View fact evidence
                  </Button>
                </div>
              ))}
            </article>
          ))}
          {detail.next_fact_cursor && (
            <Button
              disabled={busy}
              onClick={() => void open(detail.asset.id, 'fact')}
            >
              More fact history
            </Button>
          )}
        </section>
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={source.next_offset}
          opening={busy}
          onOpen={evidence}
          onClose={() => {
            generation.current++
            setBusy(false)
            setSource(null)
          }}
          request={chatRequest}
        />
      )}
    </section>
  )
}
