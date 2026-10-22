import { useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'

type Days = 30 | 90 | 365 | null
type Retention = {
  conversation_days: Days
  preview: { conversation_days: Days; eligible_count: number }
}

function parse(value: string): Days {
  return value === 'forever' ? null : (Number(value) as Days)
}

export function RetentionSettings({
  csrfToken,
  refreshSession,
}: {
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [saved, setSaved] = useState<Days | undefined>(undefined)
  const [draft, setDraft] = useState<Days>(null)
  const [eligible, setEligible] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [failed, setFailed] = useState(false)
  const request = useCallback(
    async (path: string, init?: RequestInit) => {
      const response = await fetch('/api/chat/retention' + path, {
        ...init,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
      })
      if (response.status === 401) await refreshSession?.()
      if (!response.ok) throw new Error('Retention request failed')
      return response.json()
    },
    [csrfToken, refreshSession],
  )
  useEffect(() => {
    const controller = new AbortController()
    request('', { signal: controller.signal })
      .then((data: Retention) => {
        if (controller.signal.aborted) return
        setSaved(data.conversation_days)
        setDraft(data.conversation_days)
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setFailed(true)
          setMessage('Unable to load conversation retention.')
        }
      })
    return () => controller.abort()
  }, [request])
  useEffect(() => {
    if (draft === null || draft === saved) return
    const controller = new AbortController()
    request(`?preview_days=${draft}`, { signal: controller.signal })
      .then((data: Retention) => {
        if (!controller.signal.aborted) setEligible(data.preview.eligible_count)
      })
      .catch(() => {
        if (!controller.signal.aborted) setEligible(null)
      })
    return () => controller.abort()
  }, [request, draft, saved])
  async function save() {
    setBusy(true)
    setMessage('')
    setFailed(false)
    try {
      const result = (await request('', {
        method: 'PUT',
        body: JSON.stringify({ conversation_days: draft }),
      })) as { conversation_days: Days; deleted_count: number }
      setSaved(result.conversation_days)
      setEligible(null)
      setMessage(
        result.conversation_days === null
          ? 'Conversations are kept until you delete them.'
          : `Retention saved. ${result.deleted_count} older conversation(s) deleted.`,
      )
    } catch {
      setFailed(true)
      setMessage('Unable to save retention. Please try again.')
    } finally {
      setBusy(false)
    }
  }
  const pending = draft !== null && draft !== saved && eligible !== null
  return (
    <section
      className="settings-card retention-settings"
      aria-labelledby="retention-heading"
    >
      <h2 id="retention-heading">Conversation retention</h2>
      <p>
        Automatically delete chat conversations after a period without new
        messages. Memories, sources, photos, documents and records saved from a
        conversation always stay. Deleted conversations cannot be restored.
      </p>
      <label>
        Keep conversations
        <select
          value={draft === null ? 'forever' : String(draft)}
          onChange={(e) => {
            setDraft(parse(e.target.value))
            setEligible(null)
            setMessage('')
          }}
          disabled={busy || saved === undefined}
        >
          <option value="forever">Until I delete them</option>
          <option value="30">30 days after last activity</option>
          <option value="90">90 days after last activity</option>
          <option value="365">1 year after last activity</option>
        </select>
      </label>
      {pending && (
        <p role="status">
          Saving now deletes {eligible} conversation(s) with no activity in that
          period.
        </p>
      )}
      <Button
        onClick={() => void save()}
        disabled={busy || saved === undefined || draft === saved}
      >
        {busy ? 'Saving…' : 'Save retention'}
      </Button>
      {message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
    </section>
  )
}
