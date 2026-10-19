import { useCallback, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import { GraphCanvas } from './GraphCanvas'
import { FieldHistory } from './FieldHistory'
import type { GraphData, GraphEntity, GraphFact } from './graphTypes'
import './graph.css'

type EntityPage = { items: GraphEntity[]; next_cursor: string | null }
type SourcePage = EvidenceSource & { next_offset: number | null }

export function GraphPanel({
  csrfToken,
  refreshSession,
  onOpenAsset,
  initialEntityId = '',
  onContext,
  contextRevision = 0,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
  onOpenAsset?: (id: string) => void
  initialEntityId?: string
  onContext?: (id: string | null) => void
  contextRevision?: number
}) {
  const [page, setPage] = useState<EntityPage | null>(null)
  const [selected, setSelected] = useState(initialEntityId)
  const [depth, setDepth] = useState(1)
  const [graph, setGraph] = useState<GraphData | null>(null)
  useEffect(() => {
    onContext?.(graph?.entity.id ?? null)
  }, [graph, onContext])
  const [fact, setFact] = useState<GraphFact | null>(null)
  const [source, setSource] = useState<SourcePage | null>(null)
  const [busy, setBusy] = useState(false)
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const sourceGeneration = useRef(0)
  const pagingFacts = useRef(false)
  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch(path, {
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
        throw new Error('Unable to load this private graph. Please try again.')
      return response.json()
    },
    [csrfToken, refreshSession],
  )
  useEffect(() => {
    const controller = new AbortController()
    request('/api/graph/entities', { signal: controller.signal })
      .then((next: EntityPage) => {
        if (controller.signal.aborted) return
        setPage(next)
        setSelected((current) => current || next.items[0]?.id || '')
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load graph records. Please try again.')
      })
    return () => controller.abort()
  }, [request])
  useEffect(() => {
    if (!selected) return
    const controller = new AbortController()
    const version = ++generation.current
    sourceGeneration.current++
    const timer = window.setTimeout(() => {
      setBusy(true)
      setError('')
      setGraph(null)
      setFact(null)
      setSource(null)
      setOpening(false)
      request(`/api/graph/${encodeURIComponent(selected)}?depth=${depth}`, {
        signal: controller.signal,
      })
        .then((data: GraphData) => {
          if (!controller.signal.aborted && version === generation.current)
            setGraph(data)
        })
        .catch(() => {
          if (!controller.signal.aborted)
            setError('Unable to load this private graph. Please try again.')
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false)
        })
    }, 0)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [selected, depth, request, contextRevision])
  async function entities(cursor = '') {
    try {
      setPage(
        await request(
          '/api/graph/entities?cursor=' + encodeURIComponent(cursor),
        ),
      )
    } catch {
      setError('Unable to load graph records. Please try again.')
    }
  }
  async function moreFacts() {
    if (!graph?.next_fact_cursor || pagingFacts.current) return
    pagingFacts.current = true
    const version = generation.current
    try {
      const data: GraphData = await request(
        `/api/graph/${encodeURIComponent(selected)}?depth=${depth}&fact_cursor=${encodeURIComponent(graph.next_fact_cursor)}`,
      )
      if (version === generation.current)
        setGraph((current) =>
          current
            ? {
                ...data,
                facts: [
                  ...new Map(
                    [...current.facts, ...data.facts].map((f) => [f.id, f]),
                  ).values(),
                ],
              }
            : data,
        )
    } catch {
      if (version === generation.current)
        setError('Unable to load more facts. Please try again.')
    } finally {
      pagingFacts.current = false
    }
  }
  async function openSource(id: string, offset = 0) {
    const version = ++sourceGeneration.current
    setOpening(true)
    try {
      const data: SourcePage = await request(
        `/api/chat/sources/${encodeURIComponent(id)}?offset=${offset}`,
      )
      if (version === sourceGeneration.current) setSource(data)
    } catch {
      if (version === sourceGeneration.current)
        setError('Unable to open this evidence. Please try again.')
    } finally {
      if (version === sourceGeneration.current) setOpening(false)
    }
  }
  const name = (id: string) =>
    graph?.nodes.find((node) => node.id === id)?.name ?? 'Linked record'
  return (
    <section className="graph-panel" aria-labelledby="graph-heading">
      <h1 id="graph-heading">Knowledge graph</h1>
      <p>
        Explore stored connections and their evidence. A connection is a
        recorded assertion, not proof of ownership or independently verified
        truth.
      </p>
      {error && <p role="alert">{error}</p>}
      {page?.items.length === 0 && !selected && (
        <p>
          No graph records yet. Save and review an item in Chat to begin; no
          example personal data is added.
        </p>
      )}
      {page && page.items.length > 0 && (
        <div className="graph-toolbar">
          <label>
            Focus record
            <select
              value={page.items.some((n) => n.id === selected) ? selected : ''}
              onChange={(e) => setSelected(e.target.value)}
            >
              {!page.items.some((n) => n.id === selected) && (
                <option value="">Choose a record on this page</option>
              )}
              {page.items.map((node) => (
                <option key={node.id} value={node.id}>
                  {node.name} ({node.kind})
                </option>
              ))}
            </select>
          </label>
          <Button variant="outline" onClick={() => void entities()}>
            First records
          </Button>
          {page.next_cursor && (
            <Button
              variant="outline"
              onClick={() => void entities(page.next_cursor!)}
            >
              Next records
            </Button>
          )}
          <label>
            Connection depth
            <select
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            >
              <option value={1}>Direct connections</option>
              <option value={2}>Two steps</option>
            </select>
          </label>
        </div>
      )}
      {busy && <p role="status">Loading graph…</p>}
      {graph && (
        <>
          <h2>{graph.entity.name}</h2>
          <div className="graph-toolbar">
            <Button
              variant="outline"
              onClick={() => void openSource(graph.entity.source_id)}
            >
              Open record evidence
            </Button>
            {graph.entity.kind === 'asset' && onOpenAsset && (
              <Button onClick={() => onOpenAsset(graph.entity.id)}>
                Open asset details and photos
              </Button>
            )}
          </div>
          <GraphCanvas
            graph={graph}
            onFocus={setSelected}
            onInspect={setFact}
          />
          {graph.truncated && (
            <p role="status">
              This is a bounded view; more connections may exist. Focus another
              node to explore further.
            </p>
          )}
          {!graph.edges.length && (
            <p>
              No stored entity-to-entity connections for this record yet.
              Literal facts and original evidence are listed below.
            </p>
          )}
          <details>
            <summary>Connected records as a list</summary>
            <ul>
              {graph.nodes.map((node) => (
                <li key={node.id}>
                  <Button
                    variant="outline"
                    onClick={() => setSelected(node.id)}
                  >
                    Explore {node.name}
                  </Button>{' '}
                  <span>{node.kind}</span>
                </li>
              ))}
            </ul>
          </details>
          <h3>Facts about this record</h3>
          {!graph.facts.length && <p>No current fact versions recorded.</p>}
          <ul className="graph-facts">
            {graph.facts.map((row) => (
              <li key={row.id}>
                <Button variant="outline" onClick={() => setFact(row)}>
                  {row.predicate.replaceAll('_', ' ')}:{' '}
                  {row.object_id
                    ? name(row.object_id)
                    : String(row.value ?? 'Unknown')}{' '}
                  ({row.status})
                </Button>
              </li>
            ))}
          </ul>
          {graph.next_fact_cursor && (
            <Button onClick={() => void moreFacts()}>More facts</Button>
          )}
          {fact && (
            <section className="graph-fact" aria-label="Selected connection">
              <FieldHistory
                key={`${fact.subject_id}:${fact.predicate}`}
                entityId={fact.subject_id}
                field={fact.predicate}
                onOpenSource={openSource}
              />
              <h3>{fact.predicate.replaceAll('_', ' ')}</h3>
              <p>
                {name(fact.subject_id)} →{' '}
                {fact.object_id
                  ? name(fact.object_id)
                  : String(fact.value ?? 'Unknown')}
              </p>
              <p>
                Status: <strong>{fact.status}</strong>
              </p>
              <p>
                World-valid dates: {fact.valid_from ?? 'Unknown'} to{' '}
                {fact.valid_to ?? 'Unknown or open-ended'}. Recorded{' '}
                {new Date(fact.recorded_at / 1000).toLocaleString()}.
              </p>
              {fact.evidence.map((entry, i) => (
                <div key={entry.source_id}>
                  {entry.quote && <blockquote>{entry.quote}</blockquote>}
                  <Button
                    onClick={() => void openSource(entry.source_id)}
                    disabled={opening}
                  >
                    Open evidence {i + 1}
                  </Button>
                </div>
              ))}
            </section>
          )}
        </>
      )}
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={source.next_offset}
          opening={opening}
          onOpen={openSource}
          onClose={() => {
            sourceGeneration.current++
            setSource(null)
            setOpening(false)
          }}
          request={(path, init) => request('/api/chat' + path, init)}
        />
      )}
    </section>
  )
}
