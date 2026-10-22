import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { FINDING_SAVED, researchedAt } from './researchFindings'

type Finding = {
  id: string
  question: string
  researched_at: string
  url: string
  title: string
  published: string | null
  excerpt_kind: 'source' | 'answer'
  excerpts: string[]
  recorded_at: number
  identity_note: string
}

export function AssetResearchFindings({
  assetId,
  csrfToken,
}: {
  assetId: string
  csrfToken: string
}) {
  const [items, setItems] = useState<Finding[] | null>(null)
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState('')
  const request = useCallback(
    async (signal?: AbortSignal) => {
      const response = await fetch(
        `/api/research-findings/assets/${encodeURIComponent(assetId)}`,
        { credentials: 'same-origin', cache: 'no-store', signal },
      )
      if (!response.ok)
        throw new Error('Unable to load saved research. Try refreshing.')
      return ((await response.json()) as { items: Finding[] }).items
    },
    [assetId],
  )
  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      setItems(await request())
    } catch (caught) {
      setError((caught as Error).message)
    } finally {
      setBusy(false)
    }
  }, [request])
  useEffect(() => {
    const controller = new AbortController()
    void request(controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) setItems(rows)
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setError((caught as Error).message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false)
      })
    const saved = (event: Event) => {
      if (
        (event as CustomEvent<{ assetId: string }>).detail?.assetId === assetId
      )
        void load()
    }
    window.addEventListener(FINDING_SAVED, saved)
    return () => {
      controller.abort()
      window.removeEventListener(FINDING_SAVED, saved)
    }
  }, [assetId, load, request])
  async function remove(id: string) {
    setBusy(true)
    setError('')
    try {
      const response = await fetch('/api/research-findings/remove', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ finding_id: id }),
      })
      if (!response.ok) throw new Error('Unable to remove this finding.')
      setConfirm('')
      await load()
    } catch (caught) {
      setError((caught as Error).message)
      setBusy(false)
    }
  }
  return (
    <section aria-label="Saved web research" className="asset-findings">
      <h3>Saved web research</h3>
      <p>
        Sources you saved from Chat web research. They describe a product model,
        not this item: they do not establish ownership, purchase details or
        parts compatibility.
      </p>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Loading saved research…</p>}
      {items && !items.length && !busy && (
        <p>
          No research saved yet. In Chat, research a manual or specification
          while this item is open, then save a cited source.
        </p>
      )}
      <ul>
        {items?.map((item) => (
          <li key={item.id}>
            <h4>
              <a href={item.url} target="_blank" rel="noopener noreferrer">
                {item.title}
              </a>
            </h4>
            <p className="asset-findings-meta">
              {item.published
                ? `Page dated ${item.published}`
                : 'Page date not reported'}{' '}
              · Researched {researchedAt(item.researched_at)} · Saved{' '}
              {new Date(item.recorded_at / 1000).toLocaleString()}
            </p>
            <p>Looked up: {item.question}</p>
            {item.excerpts.map((excerpt) => (
              <blockquote key={excerpt}>
                {item.excerpt_kind === 'answer' ? 'Cited for: ' : ''}
                {excerpt}
              </blockquote>
            ))}
            {confirm === item.id ? (
              <>
                <Button
                  variant="destructive"
                  disabled={busy}
                  onClick={() => void remove(item.id)}
                >
                  Confirm remove
                </Button>
                <Button variant="outline" onClick={() => setConfirm('')}>
                  Keep
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => setConfirm(item.id)}
              >
                Remove {item.title}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
