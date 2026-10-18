export type EmailLink = { purpose: 'signup' | 'reset' | 'link'; token: string }

export function readEmailLink(): EmailLink | null {
  const params = new URLSearchParams(window.location.hash.slice(1))
  const purpose = params.get('auth')
  const token = params.get('token')
  return (purpose === 'signup' || purpose === 'reset' || purpose === 'link') &&
    token &&
    token.length <= 100
    ? { purpose, token }
    : null
}
