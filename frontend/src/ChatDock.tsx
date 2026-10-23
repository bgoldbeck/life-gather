import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { Maximize2, MessageSquare, Minimize2 } from 'lucide-react'
import { DockDropZones, DockGrip } from './DockControls'
import { dockEdges as edges, useDockDrag, type Edge } from './dockDrag'
import './chatDock.css'

type Layout = { edge: Edge; collapsed: boolean; width: number; height: number }
const limits = { width: { min: 20, max: 75 }, height: { min: 25, max: 75 } }
// Below this width a side dock leaves the page too narrow, so the assistant
// sits below the page; tablets in portrait fall under it.
const narrowWidth = 1024
const phoneWidth = 600

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
  // A phone screen starts with the assistant collapsed so the page stays readable.
  return {
    edge: 'right',
    collapsed: window.innerWidth < phoneWidth,
    width: 38,
    height: 50,
  }
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
  const [narrow, setNarrow] = useState(() => window.innerWidth < narrowWidth)
  useEffect(() => {
    const update = () => {
      dragging.current = false
      setNarrow(window.innerWidth < narrowWidth)
    }
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [])
  const edge = narrow ? 'bottom' : layout.edge
  const drag = useDockDrag(workspace, !narrow, (next) => {
    dragging.current = false
    change({ ...layout, edge: next })
  })
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
      className={`workspace-body dock-${edge} ${layout.collapsed ? 'dock-collapsed' : ''} ${drag.target ? 'dock-dragging' : ''}`}
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
        <header
          className={`dock-toolbar ${narrow ? '' : 'dock-grip'}`}
          title={
            narrow
              ? 'Narrow screens keep the assistant below the page'
              : 'Drag the header to dock the assistant on another edge'
          }
          {...drag.handleProps}
        >
          {!narrow && (
            <DockGrip
              panel="assistant"
              value={layout.edge}
              onChange={(next) => change({ ...layout, edge: next })}
            />
          )}
          {layout.collapsed && (
            <MessageSquare
              className="dock-rail-icon"
              aria-hidden="true"
              size={16}
            />
          )}
          <strong>LifeGather assistant</strong>
          <button
            type="button"
            className="dock-collapse"
            aria-label={
              layout.collapsed ? 'Expand assistant' : 'Collapse assistant'
            }
            aria-expanded={!layout.collapsed}
            aria-controls="assistant-content"
            title={
              layout.collapsed
                ? 'Expand assistant'
                : 'Collapse assistant to a rail'
            }
            onClick={() => change({ ...layout, collapsed: !layout.collapsed })}
          >
            {layout.collapsed ? (
              <Maximize2 aria-hidden="true" size={14} />
            ) : (
              <Minimize2 aria-hidden="true" size={14} />
            )}
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
      <DockDropZones target={drag.target} panel="assistant" />
    </div>
  )
}
