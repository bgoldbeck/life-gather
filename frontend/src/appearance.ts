import { useEffect } from 'react'

export type Theme = 'system' | 'light' | 'dark'

export function useAppearance(theme: Theme) {
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const apply = () =>
      document.documentElement.classList.toggle(
        'dark',
        theme === 'dark' || (theme === 'system' && !!media?.matches),
      )
    apply()
    media?.addEventListener('change', apply)
    return () => {
      media?.removeEventListener('change', apply)
      document.documentElement.classList.remove('dark')
    }
  }, [theme])
}
