import { useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { FINDING_SAVED, researchedAt } from './researchFindings'

export type ResearchSource = {
  url: string
  title: string
  published: string | null
  excerpt_kind: 'source' | 'answer'
  excerpts: string[]
}
export type WebResearch = {
  researched_at: string
  queries: string[]
  searches: number
  shared_record: { id: string; name: string } | null
  sources: ResearchSource[]
  identity_note: string
}
export type SaveTarget = { id: string; name: string }

function SaveFinding({
  turnId,
  url,
  target,
  csrfToken,
}: {
  turnId: string
  url: string
  target: SaveTarget
  csrfToken: string
}) {
  const [state, setState] = useState<
    'idle' | 'saving' | 'saved' | 'removed' | 'error'
  >('idle')
  const [message, setMessage] = useState('')
  // One request ID per source and item, so a retry after a lost reply is safe.
  const requests = useRef(new Map<string, string>())
  async function save() {
    if (state === 'saving') return
    setState('saving')
    setMessage('')
    let requestId = requests.current.get(target.id)
    if (!requestId) {
      requestId = crypto.randomUUID()
      requests.current.set(target.id, requestId)
    }
    try {
      const response = await fetch('/api/research-findings', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({
          request_id: requestId,
          turn_id: turnId,
          url,
          asset_id: target.id,
        }),
      })
      if (!response.ok) {
        const detail = (await response.json().catch(() => null)) as {
          detail?: unknown
        } | null
        throw new Error(
          typeof detail?.detail === 'string'
            ? detail.detail
            : 'Unable to save this source. Try again.',
        )
      }
      const saved = (await response.json()) as {
        already_saved: boolean
        removed_at: number | null
      }
      if (saved.removed_at != null) {
        requests.current.delete(target.id)
        setState('removed')
        setMessage('Previously saved finding was removed.')
        return
      }
      setState('saved')
      setMessage(
        saved.already_saved
          ? `Already saved to ${target.name}`
          : `Saved to ${target.name}`,
      )
      window.dispatchEvent(
        new CustomEvent(FINDING_SAVED, { detail: { assetId: target.id } }),
      )
    } catch (caught) {
      setState('error')
      setMessage((caught as Error).message)
    }
  }
  return (
    <div className="chat-research-save">
      {state === 'saved' ? (
        <p role="status">{message}</p>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={state === 'saving'}
          onClick={() => void save()}
        >
          {state === 'saving'
            ? 'Saving…'
            : state === 'removed'
              ? `Save again to ${target.name}`
              : `Save to ${target.name}`}
        </Button>
      )}
      {state === 'error' && <p role="alert">{message}</p>}
      {state === 'removed' && <p role="status">{message}</p>}
    </div>
  )
}

export function ResearchResult({
  research,
  turnId,
  target,
  csrfToken,
}: {
  research: WebResearch
  turnId?: string
  target?: SaveTarget | null
  csrfToken?: string
}) {
  const canSave = !!turnId && csrfToken !== undefined
  return (
    <section className="chat-research" aria-label="Web research sources">
      <p className="chat-label">
        Researched {researchedAt(research.researched_at)} ·{' '}
        {research.shared_record
          ? `Shared saved details of ${research.shared_record.name}`
          : 'No saved record details shared'}
      </p>
      {!!research.queries.length && (
        <p>Searches run: {research.queries.join('; ')}</p>
      )}
      {!!research.sources.length && (
        <ol>
          {research.sources.map((source) => (
            <li key={source.url}>
              <a href={source.url} target="_blank" rel="noopener noreferrer">
                {source.title}
              </a>{' '}
              <span className="chat-research-date">
                {source.published
                  ? `Page dated ${source.published}`
                  : 'Page date not reported'}
              </span>
              {source.excerpts.map((excerpt) => (
                <blockquote key={excerpt}>
                  {source.excerpt_kind === 'answer' ? 'Cited for: ' : ''}
                  {excerpt}
                </blockquote>
              ))}
              {canSave && target && (
                <SaveFinding
                  key={target.id}
                  turnId={turnId}
                  url={source.url}
                  target={target}
                  csrfToken={csrfToken}
                />
              )}
            </li>
          ))}
        </ol>
      )}
      {canSave && !target && !!research.sources.length && (
        <p className="chat-research-hint">
          Open an asset to save a source to it as evidence.
        </p>
      )}
      <p role="note">{research.identity_note}</p>
    </section>
  )
}
