import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import {
  BookOpen,
  Boxes,
  Camera,
  FileText,
  Network,
  Search,
  type LucideIcon,
} from 'lucide-react'
import { ToneIcon, type Tone } from './tones'
import './global-search.css'

export type SearchResult = {
  kind: 'asset' | 'record' | 'photo' | 'document' | 'source'
  id: string
  title: string
  detail: string
  photo_id?: string | null
  document_id?: string | null
}

const groups: {
  kind: SearchResult['kind']
  label: string
  icon: LucideIcon
  tone: Tone
}[] = [
  { kind: 'asset', label: 'Assets', icon: Boxes, tone: 'assets' },
  {
    kind: 'record',
    label: 'People, places and other records',
    icon: Network,
    tone: 'graph',
  },
  { kind: 'photo', label: 'Photos', icon: Camera, tone: 'photos' },
  { kind: 'document', label: 'Documents', icon: FileText, tone: 'documents' },
  { kind: 'source', label: 'Sources', icon: BookOpen, tone: 'ai' },
]

function sourceTarget(result: SearchResult) {
  if (result.photo_id) return 'Opens its photo'
  if (result.document_id) return 'Opens its document'
  return 'Opens in Memories'
}

export function GlobalSearch({
  onOpen,
  refreshSession,
}: {
  onOpen: (result: SearchResult) => void
  refreshSession?: () => Promise<void>
}) {
  const [query, setQuery] = useState('')
  // The last answer, tagged with the words it answers; older answers are ignored.
  const [answer, setAnswer] = useState<{
    term: string
    items: SearchResult[] | null
    error: string
  }>({ term: '', items: null, error: '' })
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const term = query.trim()

  useEffect(() => {
    if (term.length < 2) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      fetch('/api/search?q=' + encodeURIComponent(term), {
        credentials: 'same-origin',
        cache: 'no-store',
        signal: controller.signal,
      })
        .then(async (response) => {
          if (response.status === 401) await refreshSession?.()
          if (response.status === 400 || response.status === 422)
            throw new Error('Use 1 to 8 words, up to 200 characters.')
          if (!response.ok)
            throw new Error('Unable to search right now. Try again.')
          return response.json()
        })
        .then((page: { items: SearchResult[] }) => {
          if (!controller.signal.aborted)
            setAnswer({ term, items: page.items, error: '' })
        })
        .catch((caught: Error) => {
          if (!controller.signal.aborted)
            setAnswer({ term, items: null, error: caught.message })
        })
    }, 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [term, refreshSession])

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  function move(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      input.current?.focus()
      return
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    const buttons = Array.from(
      root.current?.querySelectorAll<HTMLButtonElement>('[data-result]') ?? [],
    )
    if (!buttons.length) return
    event.preventDefault()
    setOpen(true)
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
    if (event.key === 'ArrowDown')
      buttons[index < 0 ? 0 : Math.min(index + 1, buttons.length - 1)].focus()
    else if (index <= 0) input.current?.focus()
    else buttons[index - 1].focus()
  }

  const showPanel = open && term.length >= 2
  const current = answer.term === term ? answer : null
  const results = current?.items ?? null
  const error = current?.error ?? ''
  const status = !current
    ? 'Searching…'
    : error
      ? ''
      : results?.length
        ? `${results.length} ${results.length === 1 ? 'match' : 'matches'}`
        : `No matches for “${term}”.`

  return (
    <div className="global-search" ref={root} onKeyDown={move}>
      <form
        role="search"
        aria-label="Search everything"
        onSubmit={(event) => {
          event.preventDefault()
          setOpen(true)
        }}
      >
        <Search aria-hidden="true" size={15} />
        <input
          ref={input}
          type="search"
          value={query}
          maxLength={200}
          placeholder="Search assets, photos, documents, sources…"
          aria-label="Search assets, photos, documents and sources"
          aria-expanded={showPanel}
          aria-controls="global-search-results"
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value)
            setOpen(true)
          }}
        />
      </form>
      {showPanel && (
        <div
          id="global-search-results"
          className="global-search-results"
          role="region"
          aria-label="Search results"
        >
          <p role="status" className="global-search-status">
            {status}
          </p>
          {error && <p role="alert">{error}</p>}
          {results &&
            groups.map(({ kind, label, icon, tone }) => {
              const items = results.filter((item) => item.kind === kind)
              if (!items.length) return null
              return (
                <section key={kind} aria-label={label}>
                  <h3>
                    <ToneIcon icon={icon} tone={tone} size={12} />
                    {label}
                  </h3>
                  <ul>
                    {items.map((item) => (
                      <li key={item.kind + item.id}>
                        <button
                          type="button"
                          data-result
                          onClick={() => {
                            setOpen(false)
                            onOpen(item)
                          }}
                        >
                          <span className="global-search-title">
                            {item.title}
                          </span>
                          <small>
                            {item.kind === 'source'
                              ? sourceTarget(item)
                              : item.detail}
                          </small>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })}
        </div>
      )}
    </div>
  )
}
