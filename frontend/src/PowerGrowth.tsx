import {
  Leaf,
  Sprout,
  TreeDeciduous,
  TreePine,
  Trees,
  type LucideIcon,
} from 'lucide-react'
import { ToneIcon } from './tones'

// Growth stages for the capability score; a workspace grows like a forest.
const stages: { name: string; from: number; icon: LucideIcon }[] = [
  { name: 'Seedling', from: 0, icon: Sprout },
  { name: 'Sapling', from: 20, icon: Leaf },
  { name: 'Growing', from: 40, icon: TreeDeciduous },
  { name: 'Thriving', from: 70, icon: TreePine },
  { name: 'Flourishing', from: 90, icon: Trees },
]

function stageFor(points: number) {
  return stages.findLast((stage) => points >= stage.from) ?? stages[0]
}

/* Shows only points the snapshot reports: confirmed points fill the bar, and an
   incomplete score shades the unverified range up to its possible maximum. */
export function PowerGrowth({
  score,
  minimum,
  maximum,
  stale,
}: {
  score: number | null
  minimum: number
  maximum: number
  stale: boolean
}) {
  const confirmed = Math.max(0, Math.min(100, score ?? minimum))
  const possible = Math.max(confirmed, Math.min(100, score ?? maximum))
  const stage = stageFor(confirmed)
  return (
    <div className={`power-growth ${stale ? 'power-growth-stale' : ''}`}>
      <div className="power-growth-heading">
        <ToneIcon icon={stage.icon} tone="assets" size={20} />
        <div>
          <span>Power level</span>
          <strong>{stale ? 'Waiting for a fresh check' : stage.name}</strong>
        </div>
        <span className="power-growth-points">
          {score === null ? `${confirmed}–${possible} pts` : `${confirmed} pts`}
        </span>
      </div>
      <div
        className="power-bar"
        role="meter"
        aria-label="Power level"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={confirmed}
        aria-valuetext={
          stale
            ? 'Stale snapshot'
            : score === null
              ? `${confirmed} confirmed points, up to ${possible} if unverified dependencies work; stage ${stage.name}`
              : `${confirmed} of 100 points; stage ${stage.name}`
        }
      >
        <span
          className="power-bar-possible"
          style={{ width: `${possible}%` }}
        />
        <span className="power-bar-fill" style={{ width: `${confirmed}%` }} />
      </div>
      <ol className="power-stages" aria-hidden="true">
        {stages.map((item) => (
          <li
            key={item.name}
            data-reached={confirmed >= item.from || undefined}
            data-current={item === stage || undefined}
          >
            <span>{item.name}</span>
            <small>{item.from}+</small>
          </li>
        ))}
      </ol>
    </div>
  )
}

// Decorative night-forest scene; colors come from the active theme's scene tokens.
export function ForestScene() {
  return (
    <svg
      className="forest-scene"
      viewBox="0 0 480 200"
      preserveAspectRatio="xMaxYMax slice"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="forest-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--scene-sky)" stopOpacity="0" />
          <stop offset="1" stopColor="var(--scene-sky)" />
        </linearGradient>
        <radialGradient id="forest-glow">
          <stop offset="0" stopColor="var(--scene-glow)" stopOpacity="0.55" />
          <stop offset="1" stopColor="var(--scene-glow)" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="480" height="200" fill="url(#forest-sky)" />
      <circle cx="345" cy="82" r="38" fill="url(#forest-glow)" />
      <circle cx="345" cy="82" r="11" fill="var(--scene-glow)" />
      <path
        d="M0 150 L70 104 L130 132 L210 84 L290 128 L360 96 L430 122 L480 104 V200 H0 Z"
        fill="var(--scene-far)"
      />
      <path
        d="M0 172 Q90 140 170 160 T330 152 T480 146 V200 H0 Z"
        fill="var(--scene-near)"
      />
      <g fill="var(--scene-trees)">
        {[
          [214, 150, 26],
          [236, 158, 34],
          [262, 152, 40],
          [292, 160, 30],
          [318, 148, 48],
          [346, 158, 36],
          [372, 150, 54],
          [402, 160, 40],
          [430, 146, 60],
          [460, 156, 46],
        ].map(([x, base, h]) => (
          <path
            key={x}
            d={`M${x} ${base - h} L${x + h * 0.28} ${base} H${x - h * 0.28} Z`}
          />
        ))}
        <path d="M180 200 Q300 170 480 176 V200 Z" />
      </g>
      <g className="forest-fireflies" fill="var(--tone-power)">
        <circle cx="250" cy="126" r="1.6" />
        <circle cx="300" cy="112" r="1.3" />
        <circle cx="356" cy="130" r="1.8" />
        <circle cx="412" cy="118" r="1.4" />
        <circle cx="448" cy="134" r="1.5" />
      </g>
    </svg>
  )
}
