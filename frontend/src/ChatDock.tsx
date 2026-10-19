import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import './chatDock.css'

type Edge = 'bottom' | 'top' | 'left' | 'right'
type Layout = { edge: Edge; collapsed: boolean; width: number; height: number }
const edges: Edge[] = ['bottom', 'top', 'left', 'right']
const limits = { width: { min: 20, max: 75 }, height: { min: 25, max: 75 } }

function savedSize(value: unknown, dimension: 'width' | 'height'): number {
  const { min, max } = limits[dimension]
  return typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= min &&
    value <= max
    ? value
    : dimension === 'width'
      ? 38
      : 50
}

function savedLayout(userId: string): Layout {
  try {
    const data = JSON.parse(
      localStorage.getItem(`lifegather-chat-dock:${userId}`) || 'null',
    )
    if (
      userId &&
      edges.includes(data?.edge) &&
      typeof data.collapsed === 'boolean'
    )
      return {
        edge: data.edge,
        collapsed: data.collapsed,
        width: savedSize(data.width, 'width'),
        height: savedSize(data.height, 'height'),
      }
  } catch {
    /* Storage may be unavailable. */
  }
  return { edge: 'right', collapsed: false, width: 38, height: 50 }
}

export function ChatDock({
  userId = '',
  children,
  page,
  expandSignal = 0,
}: {
  userId?: string
  children: ReactNode
  page: ReactNode
  expandSignal?: number
}) {
  const [layout, setLayout] = useState(() => savedLayout(userId))
  const workspace = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const [narrow, setNarrow] = useState(() => window.innerWidth <= 800)
  useEffect(() => {
    const update = () => {
      dragging.current = false
      setNarrow(window.innerWidth <= 800)
    }
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])
  const edge = narrow ? 'bottom' : layout.edge
  const vertical = edge === 'left' || edge === 'right'
  const dimension = vertical ? 'width' : 'height'
  const { min, max } = limits[dimension]
  function resize(size: number) {
    if (Number.isFinite(size))
      change({
        ...layout,
        [dimension]: Math.round(Math.max(min, Math.min(max, size))),
      })
  }
  const [lastExpand, setLastExpand] = useState(expandSignal)
  if (lastExpand !== expandSignal) {
    setLastExpand(expandSignal)
    setLayout((current) => ({ ...current, collapsed: false }))
  }
  function change(next: Layout) {
    setLayout(next)
    if (userId) {
      try {
        localStorage.setItem(
          `lifegather-chat-dock:${userId}`,
          JSON.stringify(next),
        )
      } catch {
        /* Layout still works for this session. */
      }
    }
  }
  return (
    <div
      ref={workspace}
      className={`workspace-body dock-${layout.edge} ${layout.collapsed ? 'dock-collapsed' : ''}`}
      style={
        {
          '--dock-width': `${layout.width}%`,
          '--dock-height': `${layout.height}%`,
        } as CSSProperties
      }
    >
      {page}
      <section className="assistant-dock" aria-label="LifeGather assistant">
        {!layout.collapsed && (
          <div
            className={`dock-resizer resize-${edge}`}
            role="separator"
            tabIndex={0}
            aria-label="Resize assistant"
            aria-orientation={vertical ? 'vertical' : 'horizontal'}
            aria-controls="assistant-content"
            aria-valuemin={min}
            aria-valuemax={max}
            aria-valuenow={layout[dimension]}
            aria-valuetext={`${layout[dimension]} percent ${dimension}`}
            title="Drag to resize, or focus and use arrow keys"
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
              if (!rect) return
              const extent = vertical ? rect.width : rect.height
              if (extent <= 0) return
              const distance =
                edge === 'left'
                  ? event.clientX - rect.left
                  : edge === 'right'
                    ? rect.right - event.clientX
                    : edge === 'top'
                      ? event.clientY - rect.top
                      : rect.bottom - event.clientY
              resize((distance / extent) * 100)
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
              if (event.key === 'Home') resize(min)
              else if (event.key === 'End') resize(max)
              else if (direction)
                resize(
                  layout[dimension] +
                    direction *
                      (edge === 'right' || edge === 'bottom' ? -2 : 2),
                )
              else return
              event.preventDefault()
            }}
          />
        )}
        <header className="dock-toolbar">
          <strong>LifeGather assistant</strong>
          <label>
            Dock
            <select
              aria-label="Assistant dock position"
              title="Side docks use the bottom edge on narrow screens"
              value={layout.edge}
              onChange={(e) =>
                change({ ...layout, edge: e.target.value as Edge })
              }
            >
              {edges.map((edge) => (
                <option key={edge} value={edge}>
                  {edge[0].toUpperCase() + edge.slice(1)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            aria-label={
              layout.collapsed ? 'Expand assistant' : 'Collapse assistant'
            }
            aria-expanded={!layout.collapsed}
            aria-controls="assistant-content"
            onClick={() => change({ ...layout, collapsed: !layout.collapsed })}
          >
            {layout.collapsed ? 'Expand' : 'Collapse'}
          </button>
        </header>
        <div
          id="assistant-content"
          className="dock-content"
          hidden={layout.collapsed}
        >
          {children}
        </div>
      </section>
    </div>
  )
}
