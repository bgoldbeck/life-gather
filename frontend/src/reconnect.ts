/** A sign-in the provider refused (expired or revoked) and how to renew it. */
export type ReconnectTarget = {
  kind: 'gmail' | 'ai'
  provider: string
  mailbox_id?: string | null
  credential_id?: string | null
}

/** Starts read-only Gmail consent and returns Google's validated consent URL. */
export async function startGmailConsent(csrfToken: string): Promise<string> {
  const response = await fetch('/api/mailboxes/google/start', {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken,
    },
    body: '{}',
  })
  if (!response.ok) throw new Error('Unable to start Gmail consent')
  const value: { url: string } = await response.json()
  const target = new URL(value.url)
  if (
    target.protocol !== 'https:' ||
    target.hostname !== 'accounts.google.com' ||
    target.username ||
    target.password
  )
    throw new Error('Invalid authorization redirect')
  return value.url
}

export function isReconnectTarget(value: unknown): value is ReconnectTarget {
  if (!value || typeof value !== 'object') return false
  const target = value as Record<string, unknown>
  return (
    (target.kind === 'gmail' || target.kind === 'ai') &&
    typeof target.provider === 'string'
  )
}
