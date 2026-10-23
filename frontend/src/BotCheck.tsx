import { useEffect, useRef, useState } from 'react'

type Turnstile = {
  render: (
    container: HTMLElement,
    options: {
      sitekey: string
      theme?: 'auto' | 'light' | 'dark'
      callback: (token: string) => void
      'expired-callback': () => void
      'error-callback': () => void
    },
  ) => string
  remove: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: Turnstile
  }
}

const SCRIPT =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
let loading: Promise<Turnstile> | null = null

function loadTurnstile(): Promise<Turnstile> {
  if (window.turnstile) return Promise.resolve(window.turnstile)
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT
    script.async = true
    script.onload = () =>
      window.turnstile
        ? resolve(window.turnstile)
        : reject(new Error('Bot check unavailable'))
    script.onerror = () => {
      loading = null
      script.remove()
      reject(new Error('Bot check unavailable'))
    }
    document.head.appendChild(script)
  })
  return loading
}

/** Cloudflare Turnstile, shown only when the installation configures a key.
 * Remount it (change its key) after each submit: tokens are single-use. */
export function BotCheck({
  siteKey,
  onToken,
}: {
  siteKey: string
  onToken: (token: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let widget: string | null = null
    let active = true
    onToken('')
    loadTurnstile()
      .then((turnstile) => {
        if (!active || !container.current) return
        widget = turnstile.render(container.current, {
          sitekey: siteKey,
          theme: 'auto',
          callback: (token) => {
            setFailed(false)
            onToken(token)
          },
          'expired-callback': () => onToken(''),
          'error-callback': () => {
            onToken('')
            setFailed(true)
          },
        })
      })
      .catch(() => active && setFailed(true))
    return () => {
      active = false
      if (widget !== null) window.turnstile?.remove(widget)
    }
  }, [siteKey, onToken])
  return (
    <div className="bot-check">
      <div ref={container} aria-label="Bot check" />
      {failed && (
        <p role="alert">
          The bot check could not load. Check your connection or disable
          blockers for this site, then try again.
        </p>
      )}
    </div>
  )
}
