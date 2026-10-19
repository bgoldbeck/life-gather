import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import type { Request } from './purchaseTypes'

export function PurchaseSourcePicker({
  request,
  onChoose,
  disabled,
}: {
  request: Request
  onChoose: (id: string) => void
  disabled: boolean
}) {
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState<string | null>(null)
  const [items, setItems] = useState<{ id: string; text: string }[]>([])
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)
  const [busy, setBusy] = useState(false)
  const readAbort = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    readAbort.current = controller
    void request(
      '/memories?kind=all&limit=25&query=' + encodeURIComponent(query),
      { signal: controller.signal },
    )
      .then((value) => {
        if (controller.signal.aborted) return
        const page = value as {
          items: { id: string; text: string }[]
          next_cursor: string | null
        }
        setItems(page.items)
        setCursor(page.next_cursor)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load saved sources. Refresh sources to retry.')
      })
    return () => controller.abort()
  }, [request, query, reload])
  async function more() {
    const controller = readAbort.current
    if (!cursor || busy || !controller) return
    setBusy(true)
    try {
      const page = (await request(
        '/memories?kind=all&limit=25&query=' +
          encodeURIComponent(query) +
          '&cursor=' +
          encodeURIComponent(cursor),
        { signal: controller.signal },
      )) as {
        items: { id: string; text: string }[]
        next_cursor: string | null
      }
      if (!controller.signal.aborted) {
        setItems((rows) => [...rows, ...page.items])
        setCursor(page.next_cursor)
      }
    } catch {
      if (!controller.signal.aborted) setError('Unable to load more sources.')
    } finally {
      if (!controller.signal.aborted) setBusy(false)
    }
  }
  return (
    <section
      className="space-y-2 rounded border p-3"
      aria-label="Saved purchase sources"
    >
      <h3 className="font-semibold">Choose saved evidence</h3>
      <p className="text-sm text-muted-foreground">
        Save notes or upload/import evidence first. Selecting a source only
        opens a review.
      </p>
      {error && <p role="alert">{error}</p>}
      <form
        onSubmit={(event) => {
          event.preventDefault()
          setQuery(draft)
          setReload((value) => value + 1)
          setError('')
        }}
      >
        <label>
          Search saved sources
          <input
            maxLength={200}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="ml-2 rounded border bg-background p-2"
          />
        </label>
        <Button variant="outline" type="submit" disabled={disabled || busy}>
          Refresh sources
        </Button>
      </form>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.id}>
            <Button
              type="button"
              variant="outline"
              className="h-auto max-w-full whitespace-normal text-left"
              disabled={disabled}
              onClick={() => onChoose(item.id)}
            >
              Use source: {item.text}
            </Button>
          </li>
        ))}
      </ul>
      {cursor && (
        <Button
          type="button"
          variant="outline"
          disabled={busy || disabled}
          onClick={() => void more()}
        >
          More saved sources
        </Button>
      )}
    </section>
  )
}
