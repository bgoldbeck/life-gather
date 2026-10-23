import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { EvidencePanel, type EvidenceSource } from './EvidencePanel'
import type { GraphEntity, GraphFact } from './graphTypes'
import './profiles.css'
import { FieldHistory } from './FieldHistory'
import { MaintenancePanel } from './MaintenancePanel'
import {
  customProfileName,
  editableProfileField,
  profileFields as fields,
  profileLabel,
} from './profileFields'
import { FactStatus } from './FactStatus'

type Request = (path: string, init?: RequestInit) => Promise<unknown>
type Fact = GraphFact & { superseded_at: number | null }
type Page = { entity: GraphEntity; facts: Fact[]; next_cursor: string | null }

function ProfileEditor({
  id,
  csrfToken,
  refreshSession,
  request,
  onOpenGraph,
  onContext,
  contextRevision = 0,
}: {
  id: string
  csrfToken: string
  refreshSession?: () => Promise<void>
  request: Request
  onOpenGraph?: (id: string) => void
  onContext?: (id: string | null) => void
  contextRevision?: number
}) {
  const [page, setPage] = useState<Page | null>(null)
  useEffect(() => {
    onContext?.(page?.entity.id ?? null)
  }, [page, onContext])
  const [history, setHistory] = useState(false)
  const [revision, setRevision] = useState(0)
  const [field, setField] = useState<string>('model')
  const [customName, setCustomName] = useState('')
  const [value, setValue] = useState('')
  const [text, setText] = useState('')
  const [status, setStatus] = useState('stated')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [replaces, setReplaces] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [source, setSource] = useState<
    (EvidenceSource & { next_offset: number | null }) | null
  >(null)
  const pending = useRef<{ signature: string; key: string } | null>(null)
  const active = useRef(true)
  const saving = useRef(false)
  const generation = useRef(0)
  const sourceGeneration = useRef(0)
  useEffect(() => {
    active.current = true
    return () => {
      active.current = false
    }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    generation.current++
    request(`/api/profiles/${id}?history=${history}`, {
      signal: controller.signal,
    })
      .then((result) => {
        if (!controller.signal.aborted) setPage(result as Page)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load profile details.')
      })
    return () => controller.abort()
  }, [id, history, revision, request, contextRevision])
  async function save(event: FormEvent) {
    event.preventDefault()
    if (saving.current) return
    setNotice('')
    if (field === 'custom' && customProfileName(customName) === null) {
      setError(
        'Use a custom name with letters, numbers, spaces or hyphens. For a standard detail, choose its existing type.',
      )
      return
    }
    const payload = {
      entity_id: id,
      field,
      custom_name: field === 'custom' ? customName.trim() : null,
      value: status === 'unknown' ? null : value,
      status,
      text,
      valid_from: from || null,
      valid_to: to || null,
      replaces_id: replaces,
    }
    const signature = JSON.stringify(payload)
    if (pending.current?.signature !== signature)
      pending.current = { signature, key: crypto.randomUUID() }
    saving.current = true
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await request('/api/profiles/facts', {
        method: 'POST',
        body: JSON.stringify({
          ...payload,
          operation_key: pending.current.key,
        }),
      })
      if (!active.current) return
      pending.current = null
      setRevision((n) => n + 1)
      setReplaces(null)
      setValue('')
      setText('')
      setNotice('Detail saved with original evidence.')
    } catch {
      if (active.current)
        setError(
          'Unable to save. Include the exact value in the evidence and check the detail name and dates. A corrected fact may have changed; reload before retrying.',
        )
    } finally {
      saving.current = false
      if (active.current) setBusy(false)
    }
  }
  async function openSource(sourceId: string, offset = 0) {
    const version = ++sourceGeneration.current
    try {
      const result = await request(
        `/api/chat/sources/${sourceId}?offset=${offset}`,
      )
      if (active.current && version === sourceGeneration.current)
        setSource(result as EvidenceSource & { next_offset: number | null })
    } catch {
      if (active.current) setError('Unable to open evidence.')
    }
  }
  async function more() {
    if (!page?.next_cursor || busy) return
    const version = generation.current
    setBusy(true)
    try {
      const next = (await request(
        `/api/profiles/${id}?history=${history}&cursor=${page.next_cursor}`,
      )) as Page
      if (active.current && version === generation.current)
        setPage((current) => ({
          ...next,
          facts: [
            ...new Map(
              [...(current?.facts ?? []), ...next.facts].map((row) => [
                row.id,
                row,
              ]),
            ).values(),
          ],
        }))
    } catch {
      if (active.current) setError('Unable to load more details.')
    } finally {
      if (active.current) setBusy(false)
    }
  }
  return (
    <section className="profile-editor" aria-label="Sourced profile">
      <h2>{page?.entity.name ?? 'Loading profile…'}</h2>
      <p>
        Unknown details stay unknown. A saved specification does not establish
        ownership or parts compatibility.
      </p>
      {onOpenGraph && (
        <Button variant="outline" onClick={() => onOpenGraph(id)}>
          View profile in graph
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <label>
        <input
          type="checkbox"
          checked={history}
          onChange={(e) => setHistory(e.target.checked)}
        />
        Include correction history
      </label>
      {!page?.facts.length && <p>No sourced profile details recorded.</p>}
      <ul className="profile-facts">
        {page?.facts.map((fact) => (
          <li key={fact.id}>
            <strong>{fact.label ?? profileLabel(fact.predicate)}</strong>:{' '}
            {String(fact.display_value ?? fact.value ?? 'Unknown')}{' '}
            <FactStatus status={fact.status} />{' '}
            {fact.superseded_at !== null && <span>— superseded</span>}
            <p>
              Valid: {fact.valid_from ?? 'Unknown'} to{' '}
              {fact.valid_to ?? 'Unknown or open-ended'}. Recorded{' '}
              {new Date(fact.recorded_at / 1000).toLocaleString()}.
            </p>
            {fact.evidence.map((entry) => (
              <Button
                key={entry.source_id}
                variant="outline"
                onClick={() => void openSource(entry.source_id)}
              >
                Open original evidence
              </Button>
            ))}
            <FieldHistory
              key={`${id}:${fact.predicate}:${revision}`}
              entityId={id}
              field={fact.predicate}
              onOpenSource={openSource}
            />
            {fact.superseded_at === null &&
              editableProfileField(fact.predicate) && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    const selected = editableProfileField(fact.predicate)
                    if (!selected) return
                    setField(selected.field)
                    setCustomName(selected.customName)
                    setValue(String(fact.value ?? ''))
                    setStatus(
                      fact.status === 'verified' ? 'stated' : fact.status,
                    )
                    setFrom(fact.valid_from ?? '')
                    setTo(fact.valid_to ?? '')
                    setText('')
                    setReplaces(fact.id)
                    setNotice('')
                  }}
                >
                  Correct {profileLabel(fact.predicate)}
                </Button>
              )}
          </li>
        ))}
      </ul>
      {page?.next_cursor && (
        <Button disabled={busy} onClick={() => void more()}>
          More profile details
        </Button>
      )}
      <form onSubmit={(e) => void save(e)}>
        <h3>
          {replaces ? 'Correct a sourced detail' : 'Add a sourced detail'}
        </h3>
        <label>
          Detail type
          <select
            value={field}
            disabled={!!replaces || busy}
            onChange={(e) => setField(e.target.value)}
          >
            {fields.map((item) => (
              <option key={item} value={item}>
                {item.replaceAll('_', ' ')}
              </option>
            ))}
            <option value="custom">Custom detail</option>
          </select>
        </label>
        {field === 'custom' && (
          <div>
            <label>
              Detail name
              <input
                value={customName}
                onChange={(event) => setCustomName(event.target.value)}
                maxLength={48}
                required
                disabled={busy || !!replaces}
                placeholder="For example, Tire size"
                aria-describedby="custom-detail-name-hint"
              />
            </label>
            <p id="custom-detail-name-hint">
              Use letters, numbers, spaces or hyphens. Standard details use
              their existing type.
            </p>
          </div>
        )}
        <label>
          Confidence
          <select
            value={status}
            disabled={busy}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="stated">Stated</option>
            <option value="inferred">Inferred</option>
            <option value="unknown">Unknown</option>
          </select>
        </label>
        <label>
          Exact value
          <input
            value={value}
            onChange={(e) => setValue(e.target.value)}
            maxLength={500}
            required={status !== 'unknown'}
            disabled={busy || status === 'unknown'}
          />
        </label>
        <label>
          Original evidence or your statement
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={4000}
            required
            disabled={busy}
          />
        </label>
        <p>
          Include the exact value in the text. Your statement is stored as its
          own source; it is not independently verified.
        </p>
        <label>
          Valid from (optional)
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            disabled={busy}
          />
        </label>
        <label>
          Valid until (optional, exclusive)
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            disabled={busy}
          />
        </label>
        <Button disabled={busy} type="submit">
          Save sourced detail
        </Button>
        {replaces && (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setReplaces(null)
              setValue('')
              setText('')
            }}
          >
            Cancel correction
          </Button>
        )}
      </form>
      <MaintenancePanel
        entityId={id}
        contextRevision={contextRevision}
        csrfToken={csrfToken}
        refreshSession={refreshSession}
        onOpenGraph={onOpenGraph}
      />
      {source && (
        <EvidencePanel
          key={source.id}
          source={source}
          nextOffset={source.next_offset}
          opening={false}
          onOpen={openSource}
          onClose={() => {
            sourceGeneration.current++
            setSource(null)
          }}
          request={(path, init) => request('/api/chat' + path, init)}
        />
      )}
    </section>
  )
}

export function ProfilesPanel({
  csrfToken,
  initialEntityId = '',
  refreshSession,
  onOpenGraph,
  onContext,
  contextRevision,
}: {
  csrfToken: string
  initialEntityId?: string
  refreshSession?: () => Promise<void>
  onOpenGraph?: (id: string) => void
  onContext?: (id: string | null) => void
  contextRevision?: number
}) {
  const [page, setPage] = useState<{
    items: GraphEntity[]
    next_cursor: string | null
  } | null>(null)
  const [selected, setSelected] = useState(initialEntityId)
  const [name, setName] = useState('')
  const [kind, setKind] = useState('home')
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const pending = useRef<{ signature: string; key: string } | null>(null)
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
      if (!response.ok) throw new Error('Profile request failed')
      return response.json()
    },
    [csrfToken, refreshSession],
  )
  useEffect(() => {
    const controller = new AbortController()
    request('/api/graph/entities', { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return
        setPage(data)
        setSelected(
          (id) =>
            id ||
            data.items.find((item: GraphEntity) =>
              ['asset', 'place'].includes(item.kind),
            )?.id ||
            '',
        )
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('Unable to load records.')
      })
    return () => controller.abort()
  }, [request])
  async function records(cursor = '') {
    try {
      setPage(
        await request(
          '/api/graph/entities?cursor=' + encodeURIComponent(cursor),
        ),
      )
    } catch {
      setError('Unable to load records.')
    }
  }
  async function create(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    const payload = { name, kind, text }
    const signature = JSON.stringify(payload)
    if (pending.current?.signature !== signature)
      pending.current = { signature, key: crypto.randomUUID() }
    setBusy(true)
    setError('')
    try {
      const entity = (await request('/api/profiles', {
        method: 'POST',
        body: JSON.stringify({
          ...payload,
          operation_key: pending.current.key,
        }),
      })) as GraphEntity
      setSelected(entity.id)
      setName('')
      setText('')
      pending.current = null
      await records()
    } catch {
      setError('Unable to create this record. Please try again.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="profiles-panel">
      <h1>Home and vehicle profiles</h1>
      <p>
        Select an existing asset or place to avoid duplicating it. Create a
        separate record only for a distinct home or vehicle.
      </p>
      {error && <p role="alert">{error}</p>}
      <label>
        Existing record
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">Choose an asset or place</option>
          {selected && !page?.items.some((item) => item.id === selected) && (
            <option value={selected}>Selected record</option>
          )}
          {page?.items
            .filter((n) => ['asset', 'place'].includes(n.kind))
            .map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
        </select>
      </label>
      <div className="profile-buttons">
        <Button variant="outline" onClick={() => void records()}>
          First records
        </Button>
        {page?.next_cursor && (
          <Button
            variant="outline"
            onClick={() => void records(page.next_cursor!)}
          >
            Next records
          </Button>
        )}
      </div>
      <details>
        <summary>Create a distinct home or vehicle record</summary>
        <form onSubmit={(e) => void create(e)}>
          <label>
            Record name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
              required
              disabled={busy}
            />
          </label>
          <label>
            Profile type
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              disabled={busy}
            >
              <option value="home">Home</option>
              <option value="vehicle">Vehicle</option>
            </select>
          </label>
          <label>
            Source statement
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={4000}
              required
              disabled={busy}
            />
          </label>
          <Button type="submit" disabled={busy}>
            Create separate record
          </Button>
        </form>
      </details>
      {selected && (
        <ProfileEditor
          key={selected}
          id={selected}
          csrfToken={csrfToken}
          refreshSession={refreshSession}
          request={request}
          onOpenGraph={onOpenGraph}
          onContext={onContext}
          contextRevision={contextRevision}
        />
      )}
    </section>
  )
}
