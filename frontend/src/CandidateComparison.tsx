import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import './candidate-comparison.css'
type Candidate = { id: string; name: string }
type Detail = {
  asset: { id: string; name: string; source_id: string }
  in_inventory: boolean
  decisions: {
    id: string
    manufacturer: string | null
    model: string | null
    serial: string | null
    quote: string
    source_id: string
    superseded_at: number | null
  }[]
  actions?: {
    id: string
    note: string
    source_id: string
    recorded_at: number
    direction?: string
    asset_name?: string
  }[]
  next_decision_cursor?: string | null
  next_action_cursor?: string | null
}
type Slot = {
  candidate: Candidate
  loading: boolean
  detail: Detail | null
  error: string
}
export function CandidateComparison({
  candidates,
  onOpen,
  disabled = false,
  label = 'Compare possible items',
}: {
  candidates: Candidate[]
  onOpen: (id: string) => Promise<void>
  disabled?: boolean
  label?: string
}) {
  const [page, setPage] = useState(0)
  const [slots, setSlots] = useState<Slot[]>([])
  const controllers = useRef(new Map<string, AbortController>())
  const visibleIds = useRef<string[]>([])
  useEffect(() => {
    const current = controllers.current
    return () => {
      for (const controller of current.values()) controller.abort()
    }
  }, [])
  function close(id: string) {
    visibleIds.current = visibleIds.current.filter((value) => value !== id)
    controllers.current.get(id)?.abort()
    controllers.current.delete(id)
    setSlots((current) => current.filter((slot) => slot.candidate.id !== id))
  }
  async function inspect(candidate: Candidate) {
    controllers.current.get(candidate.id)?.abort()
    const controller = new AbortController()
    controllers.current.set(candidate.id, controller)
    visibleIds.current = [
      ...visibleIds.current.filter((id) => id !== candidate.id),
      candidate.id,
    ].slice(-2)
    for (const [id, pending] of controllers.current) {
      if (!visibleIds.current.includes(id)) {
        pending.abort()
        controllers.current.delete(id)
      }
    }
    setSlots((current) =>
      [
        ...current.filter((slot) => slot.candidate.id !== candidate.id),
        { candidate, loading: true, detail: null, error: '' },
      ].slice(-2),
    )
    try {
      const response = await fetch(
        `/api/assets/${encodeURIComponent(candidate.id)}?limit=3`,
        {
          credentials: 'same-origin',
          cache: 'no-store',
          signal: controller.signal,
        },
      )
      if (!response.ok)
        throw new Error('Unable to inspect this candidate. Try again.')
      const detail: Detail = await response.json()
      if (!controller.signal.aborted)
        setSlots((current) =>
          current.map((slot) =>
            slot.candidate.id === candidate.id
              ? { ...slot, loading: false, detail, error: '' }
              : slot,
          ),
        )
    } catch {
      if (!controller.signal.aborted)
        setSlots((current) =>
          current.map((slot) =>
            slot.candidate.id === candidate.id
              ? {
                  ...slot,
                  loading: false,
                  error: 'Unable to inspect this candidate. Try again.',
                }
              : slot,
          ),
        )
    } finally {
      if (controllers.current.get(candidate.id) === controller)
        controllers.current.delete(candidate.id)
    }
  }
  if (!candidates.length) return null
  return (
    <section className="candidate-comparison" aria-label={label}>
      <h4>{label}</h4>
      <p>
        Inspect up to two records side by side. This does not select or merge
        anything. Similar names do not prove identity.
      </p>
      <div className="candidate-buttons">
        {candidates.slice(page * 5, page * 5 + 5).map((candidate) => (
          <Button
            key={candidate.id}
            variant="outline"
            disabled={disabled}
            onClick={() => void inspect(candidate)}
          >
            Inspect {candidate.name} ({candidate.id.slice(0, 8)})
          </Button>
        ))}
      </div>
      {candidates.length > 5 && (
        <div className="candidate-buttons">
          <Button
            variant="outline"
            disabled={disabled || page === 0}
            onClick={() => setPage((value) => value - 1)}
          >
            Previous candidates
          </Button>
          <span>
            Candidate page {page + 1} of {Math.ceil(candidates.length / 5)}
          </span>
          <Button
            variant="outline"
            disabled={disabled || (page + 1) * 5 >= candidates.length}
            onClick={() => setPage((value) => value + 1)}
          >
            Next candidates
          </Button>
        </div>
      )}
      <div className="candidate-grid">
        {slots.map((slot) => (
          <article
            key={slot.candidate.id}
            aria-label={`Candidate ${slot.candidate.name} (${slot.candidate.id.slice(0, 8)})`}
          >
            <h5>
              {slot.detail?.asset.name ?? slot.candidate.name} (
              {slot.candidate.id.slice(0, 8)})
            </h5>
            <Button
              variant="outline"
              disabled={disabled}
              onClick={() => close(slot.candidate.id)}
            >
              Close comparison {slot.candidate.name} (
              {slot.candidate.id.slice(0, 8)})
            </Button>
            {slot.loading && <p role="status">Loading candidate evidence…</p>}
            {slot.error && (
              <>
                <p role="alert">{slot.error}</p>
                <Button
                  variant="outline"
                  disabled={disabled}
                  onClick={() => void inspect(slot.candidate)}
                >
                  Retry inspection
                </Button>
              </>
            )}
            {slot.detail && (
              <>
                <p>
                  {slot.detail.in_inventory
                    ? 'Currently in inventory; ownership may be inferred.'
                    : 'Outside current inventory; inspect corrections and history.'}
                </p>
                <p>
                  This is a bounded snapshot, not independent verification. Your
                  final selection is still required.
                </p>
                <Button
                  variant="outline"
                  disabled={disabled}
                  onClick={() => void onOpen(slot.detail!.asset.source_id)}
                >
                  Open candidate original source
                </Button>
                <h6>Sourced identity observations</h6>
                {!slot.detail.decisions.length && (
                  <p>No identity observations found in this page.</p>
                )}
                {slot.detail.decisions.map((decision) => (
                  <div className="candidate-observation" key={decision.id}>
                    <p>
                      {decision.superseded_at === null
                        ? 'Current evidence association'
                        : 'Earlier evidence association'}
                    </p>
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
                      disabled={disabled}
                      onClick={() => void onOpen(decision.source_id)}
                    >
                      Open identity evidence
                    </Button>
                  </div>
                ))}
                {!!slot.detail.actions?.length && (
                  <>
                    <h6>Latest recorded corrections</h6>
                    {slot.detail.actions.map((action) => (
                      <div key={action.id}>
                        {action.direction === 'incoming' && (
                          <p>
                            Evidence received from{' '}
                            {action.asset_name ?? 'another item'}.
                          </p>
                        )}
                        <p>
                          Recorded{' '}
                          {new Date(action.recorded_at / 1000).toLocaleString()}
                        </p>
                        <blockquote>{action.note}</blockquote>
                        <Button
                          variant="outline"
                          disabled={disabled}
                          onClick={() => void onOpen(action.source_id)}
                        >
                          Open correction evidence
                        </Button>
                      </div>
                    ))}
                  </>
                )}
                {(slot.detail.next_decision_cursor ||
                  slot.detail.next_action_cursor) && (
                  <p>
                    More history exists. This comparison shows at most three
                    observations and three corrections; use Assets for full
                    history.
                  </p>
                )}
              </>
            )}
          </article>
        ))}
      </div>
    </section>
  )
}
