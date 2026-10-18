import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { ChatRequestError } from './chatRequest'
import { CandidateComparison } from './CandidateComparison'

type Fields = {
  name: string
  manufacturer: string | null
  model: string | null
  serial: string | null
  kind: 'purchase' | 'possession' | 'mention'
  quote: string
}
type Candidate = { id: string; name: string }
type Proposal = {
  id: string
  photo?: { id: string; deleted_at: number | null } | null
  source_id: string
  current_source_id: string
  state: 'proposed' | 'accepted' | 'rejected' | 'no_item'
  stale: boolean
  proposed: { candidate: Fields | null; explanation: string }
  reviewed: Fields | null
  automatic_outcome?: 'review'
  automatic_reason?: string
  automatic_check?: Check
  result: { asset_ids?: string[]; automatic_outcome?: string }
}
type Check = { candidates: Candidate[]; reliable_ids: string[] }

export function AssetProposalCard({
  id,
  request,
  onOpen,
  onReviewed,
}: {
  id: string
  request: (path: string, init?: RequestInit) => Promise<unknown>
  onReviewed?: () => Promise<void>
  onOpen: (id: string) => Promise<void>
}) {
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [fields, setFields] = useState<Fields | null>(null)
  const [check, setCheck] = useState<Check | null>(null)
  const [choice, setChoice] = useState('')
  const [busy, setBusy] = useState(false)
  const [retry, setRetry] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const pending = useRef<Record<string, unknown> | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    void request(`/asset-proposals/${id}`, { signal: controller.signal })
      .then((value) => {
        const row = value as Proposal
        setProposal(row)
        setFields(row.reviewed ?? row.proposed.candidate)
      })
      .catch((caught: Error) => {
        if (caught.name !== 'AbortError')
          setError(
            'Unable to load the proposal. Reopen the conversation to retry.',
          )
      })
    return () => controller.abort()
  }, [id, request])

  function edit(key: keyof Fields, value: string) {
    setFields(
      (current) =>
        current && {
          ...current,
          [key]: ['manufacturer', 'model', 'serial'].includes(key)
            ? value || null
            : value,
        },
    )
    setCheck(null)
    setChoice('')
    setError('')
    setNotice('')
  }

  async function inspect() {
    setBusy(true)
    setError('')
    try {
      const value = (await request('/asset-proposals/preview', {
        method: 'POST',
        body: JSON.stringify({ proposal_id: id, fields }),
      })) as Check
      setCheck(value)
      setChoice(value.candidates.length ? '' : 'new')
    } catch {
      setCheck(null)
      setError(
        'Check that each detail appears in the exact quote and that the note is current. Model and serial need a manufacturer.',
      )
    } finally {
      setBusy(false)
    }
  }

  async function decide(reject = false, automatic = false) {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    const operation = pending.current ?? {
      proposal_id: id,
      request_id: crypto.randomUUID(),
      action: reject
        ? 'reject'
        : automatic
          ? 'auto'
          : choice === 'new'
            ? 'new'
            : 'link',
      fields: reject ? null : fields,
      asset_id: reject || automatic || choice === 'new' ? null : choice,
      candidate_ids:
        reject || automatic ? [] : (check?.candidates.map((c) => c.id) ?? []),
    }
    pending.current = operation
    try {
      const row = (await request('/asset-proposals/review', {
        method: 'POST',
        body: JSON.stringify(operation),
      })) as Proposal
      setProposal(row)
      if (row.automatic_outcome === 'review') {
        setCheck(row.automatic_check ?? null)
        setChoice('')
        setNotice(
          'Identity needs your decision. ' +
            (row.automatic_reason ?? 'Compare the possible items below.'),
        )
      } else setFields(row.reviewed ?? row.proposed.candidate)
      pending.current = null
      setRetry(false)
      try {
        if (row.state !== 'proposed') await onReviewed?.()
      } catch {
        setError('Review saved. Refresh the queue to see updated records.')
      }
    } catch (caught) {
      if (caught instanceof ChatRequestError && caught.status < 500) {
        pending.current = null
        setRetry(false)
        setCheck(null)
        setError(
          'This proposal could not be confirmed. Reopen its evidence to check for a newer note or completed review, then check the details again.',
        )
      } else {
        setRetry(true)
        setError(
          'Connection lost. Retry checks the same decision without adding another item.',
        )
      }
    } finally {
      setBusy(false)
    }
  }

  const editable = proposal?.state === 'proposed' && !proposal.stale
  return (
    <section className="asset-proposal" aria-label="Asset proposal">
      <h3>Asset proposal</h3>
      {!proposal && !error && <p role="status">Loading proposal…</p>}
      {proposal?.photo && (
        <div>
          <p>
            AI-transcribed photo · unverified. Compare every detail with the
            image. Selecting possession or purchase is your explicit statement;
            ownership remains inferred.
          </p>
          {proposal.photo.deleted_at === null ? (
            <img
              className="photo-preview"
              src={`/api/photos/${proposal.photo.id}/preview`}
              alt="Photo supporting this proposal"
            />
          ) : (
            <p>
              The original photo was deleted. This proposal cannot be accepted.
            </p>
          )}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {error && (
        <p role="alert" className="chat-error">
          {error}
        </p>
      )}
      {proposal && (
        <>
          <p>{proposal.proposed.explanation}</p>
          <p>
            Proposed details are not verified facts. Missing prices and dates
            remain unknown.
          </p>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => void onOpen(proposal.source_id)}
          >
            View supporting note
          </Button>
          {proposal.stale && (
            <p role="status">
              The note has a newer correction. This proposal keeps its earlier
              evidence; start a new proposal from the current note.
            </p>
          )}
          {proposal.stale && (
            <Button
              variant="outline"
              onClick={() => void onOpen(proposal.current_source_id)}
            >
              View current note
            </Button>
          )}
          {proposal.state === 'accepted' && (
            <p role="status">
              Saved to inventory with source evidence. Ownership is inferred,
              not independently verified.{' '}
              {proposal.result.asset_ids?.length ?? 0} item linked.
            </p>
          )}
          {proposal.result.automatic_outcome && (
            <p>
              Recorded through a clear automatic identity check:{' '}
              {proposal.result.automatic_outcome === 'create'
                ? 'new physical item'
                : 'reliable existing identity'}
              . The source and your reviewed relationship are preserved.
            </p>
          )}
          {proposal.state === 'rejected' && (
            <p role="status">
              Proposal rejected. Your note is preserved; no inventory item was
              added.
            </p>
          )}
          {proposal.state === 'no_item' && (
            <p role="status">
              No single supported item was proposed. No inventory was changed.
            </p>
          )}
          {fields && (
            <>
              <div className="proposal-fields">
                {(['name', 'manufacturer', 'model', 'serial'] as const).map(
                  (key) => (
                    <label key={key}>
                      {
                        {
                          name: 'Item name',
                          manufacturer: 'Manufacturer',
                          model: 'Model',
                          serial: 'Serial number',
                        }[key]
                      }
                      <input
                        value={fields[key] ?? ''}
                        maxLength={key === 'name' ? 200 : 100}
                        disabled={!editable || busy || retry}
                        onChange={(event) => edit(key, event.target.value)}
                      />
                    </label>
                  ),
                )}
                <label>
                  {proposal.photo
                    ? 'Your relationship to this item'
                    : 'What the note states'}
                  <select
                    value={fields.kind}
                    disabled={!editable || busy || retry}
                    onChange={(event) => edit('kind', event.target.value)}
                  >
                    <option value="purchase">I purchased this item</option>
                    <option value="possession">I possess this item</option>
                    <option value="mention">
                      Mention only — keep out of inventory
                    </option>
                  </select>
                </label>
                <label>
                  Exact supporting quote
                  <textarea
                    rows={3}
                    value={fields.quote}
                    maxLength={2000}
                    disabled={!editable || busy || retry}
                    onChange={(event) => edit('quote', event.target.value)}
                  />
                </label>
              </div>
              {editable && (
                <>
                  <p>
                    Review the meaning as well as the words. A past purchase
                    does not prove current ownership. This first slice handles
                    one physical item per note.
                  </p>
                  <Button
                    variant="outline"
                    disabled={
                      busy ||
                      retry ||
                      !fields.name.trim() ||
                      !fields.quote.trim()
                    }
                    onClick={() => void inspect()}
                  >
                    Check details and possible duplicates
                  </Button>
                  <Button
                    variant="outline"
                    disabled={
                      busy ||
                      retry ||
                      fields.kind === 'mention' ||
                      !fields.name.trim() ||
                      !fields.quote.trim()
                    }
                    onClick={() => void decide(false, true)}
                  >
                    Record if identity is clear
                  </Button>
                  <p>
                    This uses your reviewed fields and purchase/possession
                    statement. Clear new items are recorded; reliable active
                    identifiers enrich an existing item. Similar names,
                    conflicts or previously excluded identities stay pending.
                  </p>
                  {check && (
                    <div className="proposal-identity">
                      <CandidateComparison
                        key={JSON.stringify(check.candidates)}
                        candidates={check.candidates}
                        onOpen={onOpen}
                        disabled={busy || retry}
                      />
                      <p>
                        {check.candidates.length
                          ? 'Possible existing items — a similar name or model does not prove identity. Choose explicitly.'
                          : 'No matching item found in this bounded identity check.'}
                      </p>
                      <label>
                        Physical item
                        <select
                          value={choice}
                          disabled={busy || retry}
                          onChange={(event) => setChoice(event.target.value)}
                        >
                          <option value="">
                            Choose same or different item
                          </option>
                          {!check.reliable_ids.length && (
                            <option value="new">
                              Create a different physical item
                            </option>
                          )}
                          {check.candidates.map((candidate) => (
                            <option key={candidate.id} value={candidate.id}>
                              Same item: {candidate.name} (
                              {candidate.id.slice(0, 8)})
                            </option>
                          ))}
                        </select>
                      </label>
                      {check.reliable_ids.length > 0 && (
                        <p>
                          An identifier matches an existing item. Review that
                          item instead of creating another.
                        </p>
                      )}
                    </div>
                  )}
                  <div className="note-actions">
                    <Button
                      disabled={
                        busy ||
                        (!retry &&
                          (!check || !choice || fields.kind === 'mention'))
                      }
                      onClick={() => void decide()}
                    >
                      {busy
                        ? 'Saving decision…'
                        : retry
                          ? 'Retry same decision'
                          : 'Confirm asset'}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={busy || retry}
                      onClick={() => void decide(true)}
                    >
                      Reject proposal
                    </Button>
                  </div>
                </>
              )}
              {proposal.stale && proposal.state === 'proposed' && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => void decide(true)}
                >
                  Reject earlier proposal
                </Button>
              )}
            </>
          )}
        </>
      )}
    </section>
  )
}
