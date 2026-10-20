import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import './navigationDock.css'

type Edge = 'left' | 'right' | 'top' | 'bottom'
type Layout = { edge: Edge; width: number; height: number }
type Props = { userId: string; navigation: ReactNode; children: ReactNode }
const defaults: Layout = { edge: 'left', width: 244, height: 160 }
const edges: Edge[] = ['left', 'right', 'top', 'bottom']
const minimum = { width: 200, height: 112 }
const maximum = { width: 400, height: 320 }

function savedLayout(userId: string): Layout {
  if (!userId) return defaults
  try {
    const value = JSON.parse(
      localStorage.getItem(`lifegather-navigation-dock:${userId}`) ?? 'null',
    )
    if (!edges.includes(value?.edge)) return defaults
    const dimension = (name: 'width' | 'height') =>
      typeof value[name] === 'number' &&
      Number.isFinite(value[name]) &&
      value[name] >= minimum[name] &&
      value[name] <= maximum[name]
        ? value[name]
        : defaults[name]
    return {
      edge: value.edge,
      width: dimension('width'),
      height: dimension('height'),
    }
  } catch {
    return defaults
  }
}

// The account key also prevents layout state crossing a direct account switch.
export function NavigationDock(props: Props) {
  return <NavigationLayout key={props.userId} {...props} />
}

function NavigationLayout({ userId, navigation, children }: Props) {
  const [layout, setLayout] = useState(() => savedLayout(userId))
  const [viewport, setViewport] = useState(() => ({
    width: window.innerWidth,
    height: window.innerHeight,
  }))
  const workspace = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  useEffect(() => {
    const resized = () => {
      dragging.current = false
      setViewport({ width: window.innerWidth, height: window.innerHeight })
    }
    window.addEventListener('resize', resized)
    return () => window.removeEventListener('resize', resized)
  }, [])
  const compact = viewport.width <= 800
  const edge = compact ? 'top' : layout.edge
  const vertical = edge === 'left' || edge === 'right'
  const dimension = vertical ? 'width' : 'height'
  const max = Math.max(
    minimum[dimension],
    Math.min(
      maximum[dimension],
      Math.floor(viewport[dimension] * (vertical ? 0.32 : 0.35)),
    ),
  )
  const size = Math.min(layout[dimension], max)
  function change(next: Layout) {
    setLayout(next)
    if (userId) {
      try {
        localStorage.setItem(
          `lifegather-navigation-dock:${userId}`,
          JSON.stringify(next),
        )
      } catch {
        /* Keep layout usable when browser preference storage is unavailable. */
      }
    }
  }
  function resize(value: number) {
    if (Number.isFinite(value))
      change({
        ...layout,
        [dimension]: Math.round(
          Math.max(minimum[dimension], Math.min(max, value)),
        ),
      })
  }
  return (
    <div
      ref={workspace}
      className={`app-layout navigation-shell navigation-${edge} ${compact ? 'navigation-compact' : ''}`}
      style={
        {
          '--navigation-width': `${vertical ? size : layout.width}px`,
          '--navigation-height': `${vertical ? layout.height : size}px`,
        } as CSSProperties
      }
    >
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <div className="navigation-panel">
        <aside
          className="sidebar"
          id="primary-navigation-panel"
          aria-label="Workspace navigation"
        >
          <div className="navigation-controls">
            <label>
              Dock
              <select
                aria-label="Navigation dock position"
                value={layout.edge}
                title="Choose a desktop edge; compact screens keep navigation above content"
                onChange={(event) => {
                  dragging.current = false
                  change({ ...layout, edge: event.target.value as Edge })
                }}
              >
                {edges.map((option) => (
                  <option key={option} value={option}>
                    {option[0].toUpperCase() + option.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="Reset navigation layout"
              title="Reset navigation to the left and default dimensions"
              onClick={() => {
                dragging.current = false
                change(defaults)
              }}
            >
              <RotateCcw aria-hidden="true" size={15} />
            </Button>
          </div>
          {navigation}
        </aside>
        {!compact && (
          <div
            role="separator"
            tabIndex={0}
            className={`navigation-resizer navigation-resize-${edge}`}
            aria-label="Resize navigation"
            aria-controls="primary-navigation-panel"
            aria-orientation={vertical ? 'vertical' : 'horizontal'}
            aria-valuemin={minimum[dimension]}
            aria-valuemax={max}
            aria-valuenow={size}
            aria-valuetext={`${size} pixels ${dimension}`}
            title="Drag to resize, or focus and use arrows, Home or End"
            onPointerDown={(event) => {
              if (event.button !== 0) return
              event.preventDefault()
              event.currentTarget.focus()
              event.currentTarget.setPointerCapture?.(event.pointerId)
              dragging.current = true
            }}
            onPointerMove={(event) => {
              if (!dragging.current) return
              const rect = workspace.current?.getBoundingClientRect()
              if (!rect || rect.width <= 0 || rect.height <= 0) return
              resize(
                edge === 'left'
                  ? event.clientX - rect.left
                  : edge === 'right'
                    ? rect.right - event.clientX
                    : edge === 'top'
                      ? event.clientY - rect.top
                      : rect.bottom - event.clientY,
              )
            }}
            onPointerUp={(event) => {
              dragging.current = false
              if (event.currentTarget.hasPointerCapture?.(event.pointerId))
                event.currentTarget.releasePointerCapture(event.pointerId)
            }}
            onPointerCancel={() => {
              dragging.current = false
            }}
            onLostPointerCapture={() => {
              dragging.current = false
            }}
            onKeyDown={(event) => {
              const direction = vertical
                ? { ArrowLeft: -1, ArrowRight: 1 }[event.key]
                : { ArrowUp: -1, ArrowDown: 1 }[event.key]
              if (event.key === 'Home') resize(minimum[dimension])
              else if (event.key === 'End') resize(max)
              else if (direction)
                resize(
                  size +
                    direction *
                      (edge === 'right' || edge === 'bottom' ? -1 : 1) *
                      (event.shiftKey ? 50 : 10),
                )
              else return
              event.preventDefault()
            }}
          />
        )}
      </div>
      {children}
    </div>
  )
}
