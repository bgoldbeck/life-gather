import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ChatRequestError } from './chatRequest'

type Preview = {
  format: 'lifegather-conversation-deletion/1'
  id: string
  title: string
  turn_count: number
  pending_count: number
  preview_token: string
}

function previewData(value: unknown, id: string): Preview {
  const row = value as Partial<Preview> | null
  if (
    !row ||
    typeof row !== 'object' ||
    row.format !== 'lifegather-conversation-deletion/1' ||
    row.id !== id ||
    typeof row.title !== 'string' ||
    typeof row.turn_count !== 'number' ||
    !Number.isSafeInteger(row.turn_count) ||
    row.turn_count < 0 ||
    typeof row.pending_count !== 'number' ||
    !Number.isSafeInteger(row.pending_count) ||
    row.pending_count < 0 ||
    row.pending_count > row.turn_count ||
    typeof row.preview_token !== 'string' ||
    !/^[a-f0-9]{64}$/.test(row.preview_token)
  )
    throw new Error('Invalid deletion preview')
  return row as Preview
}

export function ConversationDelete({
  id,
  title,
  request,
  onDeleted,
  onCancel,
}: {
  id: string
  title: string
  request: (path: string, init?: RequestInit) => Promise<unknown>
  onDeleted: (id: string) => void
  onCancel: () => void
}) {
  const [preview, setPreview] = useState<Preview | null>(null)
  const [review, setReview] = useState(0)
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [finished, setFinished] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const active = useRef<AbortController | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const base = `/conversations/${encodeURIComponent(id)}`

  useEffect(() => {
    heading.current?.focus()
  }, [id])
  useEffect(() => {
    const controller = new AbortController()
    active.current = controller
    void request(`${base}/deletion-preview`, {
      method: 'POST',
      body: '{}',
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) {
          setPreview(previewData(data, id))
          setConfirmed(false)
          setError('')
          setNotice('')
        }
      })
      .catch((caught) => {
        if (!controller.signal.aborted) {
          setPreview(null)
          setConfirmed(false)
          setError(
            caught instanceof ChatRequestError && caught.status === 401
              ? 'Your session expired. Sign in again before deleting.'
              : 'Unable to prepare deletion. Review it again or try later.',
          )
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          if (active.current === controller) active.current = null
          setLoading(false)
        }
      })
    return () => {
      controller.abort()
      active.current?.abort()
    }
  }, [base, id, request, review])

  async function mutate(stop: boolean) {
    if (
      active.current ||
      !preview ||
      preview.id !== id ||
      finished ||
      (!stop && (!confirmed || preview.pending_count))
    )
      return
    const controller = new AbortController()
    active.current = controller
    setWorking(true)
    setError('')
    setNotice('')
    try {
      const result = await request(
        `${base}/${stop ? 'stop-pending' : 'delete'}`,
        {
          method: 'POST',
          signal: controller.signal,
          body: JSON.stringify({
            preview_token: preview.preview_token,
            ...(stop ? {} : { confirmed: true }),
          }),
        },
      )
      if (controller.signal.aborted) return
      setConfirmed(false)
      if (stop) {
        const next = previewData(result, id)
        setPreview(next)
        setNotice(
          next.pending_count
            ? 'Review the remaining pending requests.'
            : 'No pending chat requests remain. Review deletion below.',
        )
      } else {
        if (
          !result ||
          typeof result !== 'object' ||
          !('id' in result) ||
          result.id !== id ||
          !('deleted' in result) ||
          result.deleted !== true
        )
          throw new Error('Invalid deletion response')
        setFinished(true)
        onDeleted(id)
      }
    } catch (caught) {
      if (controller.signal.aborted) return
      setConfirmed(false)
      if (caught instanceof ChatRequestError && caught.status === 409) {
        setPreview(null)
        setError('Conversation changed. Review it again before continuing.')
      } else
        setError(
          caught instanceof ChatRequestError && caught.status === 401
            ? 'Your session expired. Sign in again before deleting.'
            : 'Unable to finish. Review the conversation again before retrying.',
        )
    } finally {
      if (!controller.signal.aborted) {
        if (active.current === controller) active.current = null
        setWorking(false)
      }
    }
  }

  return (
    <section
      className="conversation-delete"
      aria-label="Review conversation deletion"
      aria-busy={loading || working}
    >
      <h2 ref={heading} tabIndex={-1}>
        Delete conversation: {preview?.title ?? title}
      </h2>
      <p>
        Delete this conversation’s saved requests and assistant replies
        permanently. This cannot be undone here.
      </p>
      <p>
        Saved memories, profile changes, purchases, files, scans, settings and
        usage remain. Existing exports, backups and provider history are
        unchanged.
      </p>
      {loading && <p role="status">Preparing deletion preview…</p>}
      {preview && (
        <>
          <p>
            {preview.turn_count} saved{' '}
            {preview.turn_count === 1 ? 'request' : 'requests'} and their
            replies.
          </p>
          {preview.pending_count > 0 && (
            <>
              <p>
                {preview.pending_count} pending chat{' '}
                {preview.pending_count === 1
                  ? 'request needs'
                  : 'requests need'}{' '}
                stopping before deletion. This includes interrupted requests.
                Created scan jobs remain in Scans.
              </p>
              <Button
                variant="outline"
                disabled={working || finished}
                onClick={() => void mutate(true)}
              >
                Stop pending chat requests
              </Button>
            </>
          )}
          <label className="consent-label">
            <input
              type="checkbox"
              checked={confirmed}
              disabled={working || finished || preview.pending_count > 0}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            Permanently delete this conversation
          </label>
          <Button
            variant="destructive"
            disabled={
              working || finished || !confirmed || preview.pending_count > 0
            }
            onClick={() => void mutate(false)}
          >
            Delete permanently
          </Button>
        </>
      )}
      {working && <p role="status">Finishing your request…</p>}
      {finished && <p role="status">Conversation deleted.</p>}
      {notice && <p role="status">{notice}</p>}
      {error && (
        <>
          <p role="alert">{error}</p>
          <Button
            variant="outline"
            disabled={loading || working || finished}
            onClick={() => {
              setLoading(true)
              setPreview(null)
              setConfirmed(false)
              setError('')
              setNotice('')
              setReview((value) => value + 1)
            }}
          >
            Review again
          </Button>
        </>
      )}
      <Button
        variant="outline"
        disabled={working || finished}
        onClick={onCancel}
      >
        Cancel deletion
      </Button>
    </section>
  )
}
