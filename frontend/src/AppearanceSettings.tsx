import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { Theme } from './appearance'

export function AppearanceSettings({
  theme = 'system',
  csrfToken,
  refreshSession,
}: {
  theme?: Theme
  csrfToken: string
  refreshSession?: () => Promise<void>
}) {
  const [draft, setValue] = useState<Theme | null>(null)
  const value = draft ?? theme
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [failed, setFailed] = useState(false)
  async function save() {
    setBusy(true)
    setMessage('')
    setFailed(false)
    try {
      const response = await fetch('/api/appearance', {
        method: 'PUT',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify({ theme: value }),
      })
      if (!response.ok) throw new Error('Save failed')
      await refreshSession?.()
      setValue(null)
      setMessage('Appearance saved.')
    } catch {
      setFailed(true)
      setMessage('Unable to save appearance. Please try again.')
    } finally {
      setBusy(false)
    }
  }
  return (
    <section
      className="settings-card appearance-settings"
      aria-labelledby="appearance-heading"
    >
      <h2 id="appearance-heading">Appearance</h2>
      <p>Choose your personal color theme. System follows your device.</p>
      <label>
        Color theme
        <select
          value={value}
          onChange={(e) => setValue(e.target.value as Theme)}
          disabled={busy}
        >
          <option value="system">System</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
          <option value="forest-dark">Forest dark</option>
        </select>
      </label>
      <Button onClick={() => void save()} disabled={busy}>
        {busy ? 'Saving…' : 'Save appearance'}
      </Button>
      {message && <p role={failed ? 'alert' : 'status'}>{message}</p>}
    </section>
  )
}
