import { useState } from 'react'
import { Undo2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import './undo.css'

// A reversible change offers one recorded undo until the next change replaces it.
export type UndoAction = {
  message: string
  label: string
  // Resolves with the status to show once the undo is saved.
  run: () => Promise<string>
}

export function UndoNotice({
  action,
  disabled = false,
  onBusy,
  onDone,
}: {
  action: UndoAction
  disabled?: boolean
  onBusy?: (busy: boolean) => void
  onDone: (status: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function undo() {
    if (busy || disabled) return
    setBusy(true)
    onBusy?.(true)
    setError('')
    try {
      onDone(await action.run())
    } catch (caught) {
      setError(
        (caught as Error).message ||
          'Undo was not confirmed. Refresh to check the current state.',
      )
    } finally {
      setBusy(false)
      onBusy?.(false)
    }
  }
  return (
    <div className="undo-notice">
      <p role="status">{action.message}</p>
      <Button
        variant="outline"
        size="sm"
        aria-label={action.label}
        disabled={busy || disabled}
        onClick={() => void undo()}
      >
        <Undo2 aria-hidden="true" size={14} />
        {busy ? 'Undoing…' : 'Undo'}
      </Button>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
