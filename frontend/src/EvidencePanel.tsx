import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { ChatRequestError } from './chatRequest'

export type EvidenceSource = {
  id: string
  text: string
  photo?: { id: string; deleted_at: number | null } | null
  document?: { id: string; filename: string; deleted_at: number | null } | null
  receipt_proposal_id?: string | null
  asset_proposal_id?: string | null
  maintenance_context?: {
    task_id: string
    revision_id: string
    is_current_revision: boolean
    current_source_id: string
    target: { id: string; name: string; kind: string }
    state: string
    due_on: string | null
    completed_on: string | null
    timezone: string
  } | null
  asset_context?: {
    asset_name: string
    operation: string
    user_selected_status: string | null
    ownership_statement_current_version?: boolean
    replacement_statement_current_version?: boolean
    association_versions_current?: number
    association_versions_total?: number
    target_asset_name?: string | null
  } | null
  note?: {
    root_source_id: string
    current_source_id: string
    is_current: boolean
    can_correct: boolean
  } | null
}
type Version = {
  id: string
  text: string
  recorded_at: number
  is_current: boolean
  is_original: boolean
}
type HistoryPage = { items: Version[]; next_cursor: string | null }

export function EvidencePanel({
  source,
  nextOffset,
  opening,
  onOpen,
  onClose,
  request,
  onSuggest,
  onViewProposal,
  onSuggestReceipt,
  onViewReceipt,
}: {
  source: EvidenceSource
  nextOffset: number | null
  opening: boolean
  onOpen: (id: string, offset?: number) => Promise<void>
  onClose: () => void
  request: (path: string, init?: RequestInit) => Promise<unknown>
  onSuggestReceipt?: () => void
  onViewReceipt?: (id: string) => void
  onSuggest?: () => void
  onViewProposal?: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(source.text)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [retrying, setRetrying] = useState(false)
  const [history, setHistory] = useState<HistoryPage | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const pending = useRef<{ request_id: string; text: string } | null>(null)
  const controller = useRef<AbortController | null>(null)
  useEffect(() => () => controller.current?.abort(), [])

  async function loadHistory(cursor?: string) {
    setHistoryLoading(true)
    setError('')
    try {
      const page = (await request(
        `/sources/${source.id}/history${cursor ? '?cursor=' + cursor : ''}`,
      )) as HistoryPage
      setHistory((current) => ({
        items:
          cursor && current ? [...current.items, ...page.items] : page.items,
        next_cursor: page.next_cursor,
      }))
    } catch {
      setError('Unable to load note history. Please try again.')
    } finally {
      setHistoryLoading(false)
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    if (saving || !draft.trim() || draft === source.text) return
    setSaving(true)
    setError('')
    const operation = pending.current ?? {
      request_id: crypto.randomUUID(),
      text: draft,
    }
    pending.current = operation
    const abort = new AbortController()
    controller.current = abort
    try {
      const result = (await request(`/sources/${source.id}/corrections`, {
        method: 'POST',
        body: JSON.stringify(operation),
        signal: abort.signal,
      })) as { source: { id: string } }
      pending.current = null
      setRetrying(false)
      setEditing(false)
      await onOpen(result.source.id)
    } catch (caught) {
      if (caught instanceof ChatRequestError) {
        pending.current = null
        setRetrying(false)
        if (caught.status === 409) {
          setError(
            'This note changed in another request. Open its current version before correcting it.',
          )
          setEditing(false)
          await onOpen(source.id)
        } else
          setError(
            'Unable to save the correction. Your original note is preserved.',
          )
      } else if ((caught as Error).name !== 'AbortError') {
        setRetrying(true)
        setError(
          'Connection lost. Retry safely checks this correction without creating another version.',
        )
      }
    } finally {
      setSaving(false)
      controller.current = null
    }
  }

  return (
    <section className="chat-evidence" aria-label="Original evidence">
      <div className="evidence-heading">
        <h2>Original evidence</h2>
        <Button variant="ghost" disabled={saving} onClick={onClose}>
          Close evidence
        </Button>
      </div>
      {source.photo ? (
        <div>
          <p>
            AI photo transcription or correction · unverified. Compare with the
            original image.
          </p>
          {source.photo.deleted_at === null ? (
            <img
              className="photo-preview"
              src={`/api/photos/${source.photo.id}/preview`}
              alt="Original photo preview"
            />
          ) : (
            <p>The original photo has been deleted. Derived text remains.</p>
          )}
        </div>
      ) : source.document ? (
        <p>Reviewed PDF text or correction · not independently verified</p>
      ) : (
        <p>Original statement · not independently verified</p>
      )}
      {source.note && (
        <p role="status">
          {source.note.is_current
            ? 'Current saved note'
            : 'Earlier version — a newer correction is available.'}
        </p>
      )}
      {source.maintenance_context && (
        <div>
          <p role="status">
            {source.maintenance_context.is_current_revision
              ? 'Current maintenance statement'
              : 'Earlier maintenance statement — a newer revision is available.'}
          </p>
          <p>
            {source.maintenance_context.target.name} · Recorded task state:{' '}
            {source.maintenance_context.state}. Due date:{' '}
            {source.maintenance_context.due_on ?? 'Unknown'}. Completion date:{' '}
            {source.maintenance_context.completed_on ?? 'Unknown'} ·{' '}
            {source.maintenance_context.timezone}.
          </p>
          {!source.maintenance_context.is_current_revision && (
            <Button
              variant="outline"
              disabled={opening || saving}
              onClick={() =>
                void onOpen(source.maintenance_context!.current_source_id)
              }
            >
              View current maintenance statement
            </Button>
          )}
        </div>
      )}
      <p className="chat-text">{source.text}</p>
      {source.document && (
        <div>
          <p>
            Reviewed PDF text: {source.document.filename}. Text may omit layout
            or scanned content.
          </p>
          {source.document.deleted_at === null ? (
            <a href={`/api/documents/${source.document.id}/original`} download>
              Download original PDF
            </a>
          ) : (
            <p>
              The original PDF has been deleted; saved source history remains.
            </p>
          )}
        </div>
      )}
      {source.asset_context && (
        <p>
          Recorded against {source.asset_context.asset_name}. User-selected
          statement:{' '}
          {(
            source.asset_context.user_selected_status ??
            source.asset_context.operation
          ).replaceAll('_', ' ')}
          .
        </p>
      )}
      {source.asset_context?.target_asset_name && (
        <p>
          {source.asset_context.operation.startsWith('replacement')
            ? 'Replacement item'
            : source.asset_context.operation === 'batch_restore'
              ? 'Evidence returned from'
              : 'Receiving item'}
          : {source.asset_context.target_asset_name}.
        </p>
      )}
      {source.asset_context?.ownership_statement_current_version === false && (
        <p>
          This ownership statement has been superseded. Inspect the item's
          current facts and history.
        </p>
      )}
      {source.asset_context?.replacement_statement_current_version ===
        false && (
        <p>
          The linked replacement statement has been superseded or withdrawn.
        </p>
      )}
      {source.asset_context?.association_versions_total !== undefined &&
        (source.asset_context.association_versions_current ?? 0) <
          source.asset_context.association_versions_total && (
          <p>
            Only {source.asset_context.association_versions_current ?? 0} of{' '}
            {source.asset_context.association_versions_total} recorded
            association versions remain current. Inspect item history for the
            current unit mappings.
          </p>
        )}
      {source.asset_proposal_id && onViewProposal && (
        <Button
          variant="outline"
          disabled={saving}
          onClick={() => onViewProposal(source.asset_proposal_id!)}
        >
          View asset proposal
        </Button>
      )}
      {!source.asset_proposal_id && source.note?.is_current && onSuggest && (
        <Button
          variant="outline"
          disabled={saving || opening || editing}
          onClick={onSuggest}
        >
          Suggest an asset from this note
        </Button>
      )}
      {source.receipt_proposal_id && onViewReceipt && (
        <Button
          variant="outline"
          disabled={saving}
          onClick={() => onViewReceipt(source.receipt_proposal_id!)}
        >
          View receipt review
        </Button>
      )}
      {source.note?.is_current &&
        onSuggestReceipt &&
        !source.receipt_proposal_id && (
          <Button
            variant="outline"
            disabled={opening || saving}
            onClick={onSuggestReceipt}
          >
            Review multiple items from this note
          </Button>
        )}
      {nextOffset !== null && (
        <Button
          disabled={opening || saving}
          onClick={() => void onOpen(source.id, nextOffset)}
        >
          Next source page
        </Button>
      )}
      {source.note && (
        <div className="note-actions">
          {!source.note.is_current && (
            <Button
              disabled={opening || saving}
              variant="outline"
              onClick={() => void onOpen(source.note!.current_source_id)}
            >
              View current note
            </Button>
          )}
          {source.note.can_correct && !editing && (
            <Button
              variant="outline"
              disabled={opening}
              onClick={() => {
                setDraft(source.text)
                setEditing(true)
                setError('')
              }}
            >
              Correct note
            </Button>
          )}
          <Button
            variant="outline"
            disabled={historyLoading || saving}
            onClick={() => void loadHistory()}
          >
            View note history
          </Button>
        </div>
      )}
      {editing && source.note?.can_correct && (
        <form
          className="note-correction"
          onSubmit={(event) => void save(event)}
        >
          <label htmlFor="note-correction">Corrected note</label>
          <textarea
            id="note-correction"
            value={draft}
            maxLength={4000}
            rows={4}
            disabled={saving || retrying}
            onChange={(event) => setDraft(event.target.value)}
          />
          <p>
            The previous text stays in history. This changes your saved note; it
            does not change inventory or graph facts.
          </p>
          <div className="note-actions">
            <Button
              type="submit"
              disabled={saving || !draft.trim() || draft === source.text}
            >
              {saving
                ? 'Saving correction…'
                : retrying
                  ? 'Retry correction'
                  : 'Save correction'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              disabled={saving}
              onClick={() => {
                setEditing(false)
                pending.current = null
                setRetrying(false)
                setError('')
              }}
            >
              Cancel correction
            </Button>
          </div>
        </form>
      )}
      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}
      {historyLoading && <p role="status">Loading note history…</p>}
      {history && (
        <section className="note-history" aria-label="Note history">
          <h3>Note history</h3>
          <p>
            Saved order shows when a correction was recorded, not when a fact
            became true.
          </p>
          <ol>
            {history.items.map((version) => (
              <li key={version.id}>
                <Button
                  variant="ghost"
                  disabled={opening || saving}
                  onClick={() => void onOpen(version.id)}
                >
                  <span>
                    {version.is_original ? 'Original' : 'Correction'}
                    {version.is_current ? ' · Current' : ''} ·{' '}
                    {new Date(version.recorded_at / 1000).toLocaleString()}
                    <br />
                    {version.text}
                  </span>
                </Button>
              </li>
            ))}
          </ol>
          {history.next_cursor && (
            <Button
              variant="outline"
              disabled={historyLoading}
              onClick={() => void loadHistory(history.next_cursor!)}
            >
              More note history
            </Button>
          )}
        </section>
      )}
    </section>
  )
}
