import { useEffect } from 'react'

export type Theme = 'system' | 'light' | 'dark' | 'forest-dark'

export function useAppearance(theme: Theme) {
  useEffect(() => {
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const root = document.documentElement
    const apply = () => {
      const forest = theme === 'forest-dark'
      root.classList.toggle(
        'dark',
        forest || theme === 'dark' || (theme === 'system' && !!media?.matches),
      )
      root.classList.toggle('forest', forest)
    }
    apply()
    media?.addEventListener('change', apply)
    return () => {
      media?.removeEventListener('change', apply)
      root.classList.remove('dark', 'forest')
    }
  }, [theme])
}
