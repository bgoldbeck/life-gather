import type { LucideIcon } from 'lucide-react'
import './tones.css'

// One accent per area of the app; values are defined per theme in tones.css.
export type Tone =
  | 'power'
  | 'email'
  | 'finance'
  | 'documents'
  | 'photos'
  | 'assets'
  | 'maintenance'
  | 'ai'
  | 'graph'
  | 'settings'

export function ToneIcon({
  icon: Icon,
  tone,
  size = 18,
  className = '',
}: {
  icon: LucideIcon
  tone: Tone
  size?: number
  className?: string
}) {
  return (
    <span className={`tone-tile ${className}`} data-tone={tone}>
      <Icon aria-hidden="true" size={size} />
    </span>
  )
}
