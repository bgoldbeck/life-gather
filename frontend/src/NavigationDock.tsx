import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { PanelLeftClose, PanelLeftOpen, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { DockDropZones, DockEdgeButtons } from './DockControls'
import { dockEdges as edges, useDockDrag, type Edge } from './dockDrag'
import './navigationDock.css'

type Layout = { edge: Edge; width: number; height: number; collapsed: boolean }
type Props = { userId: string; navigation: ReactNode; children: ReactNode }
const defaults: Layout = {
  edge: 'left',
  width: 216,
  height: 160,
  collapsed: false,
}
// Collapsed navigation keeps a thin icon rail on its edge.
const rail = { width: 60, height: 56 }
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
      // Layouts saved before the icon rail have no collapsed flag.
      collapsed: value.collapsed === true,
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
  const collapsed = layout.collapsed && !compact
  const drag = useDockDrag(workspace, !compact, (next) => {
    dragging.current = false
    change({ ...layout, edge: next })
  })
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
      className={`app-layout navigation-shell navigation-${edge} ${compact ? 'navigation-compact' : ''} ${collapsed ? 'navigation-collapsed' : ''} ${drag.target ? 'dock-dragging' : ''}`}
      style={
        {
          '--navigation-width': `${collapsed ? rail.width : vertical ? size : layout.width}px`,
          '--navigation-height': `${collapsed ? rail.height : vertical ? layout.height : size}px`,
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
          onPointerDown={(event) => {
            // The brand and control row act as the panel's drag header.
            if (
              (event.target as Element).closest('.brand, .navigation-controls')
            )
              drag.handleProps.onPointerDown(event)
          }}
          onPointerMove={drag.handleProps.onPointerMove}
          onPointerUp={drag.handleProps.onPointerUp}
          onPointerCancel={drag.handleProps.onPointerCancel}
        >
          <div
            className="navigation-controls"
            title={
              compact
                ? 'Compact screens keep navigation above content'
                : 'Drag the header to dock navigation on another edge'
            }
          >
            {!collapsed && !compact && (
              <>
                <DockEdgeButtons
                  panel="navigation"
                  value={layout.edge}
                  onChange={(next) => {
                    dragging.current = false
                    change({ ...layout, edge: next })
                  }}
                />
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
              </>
            )}
            {!compact && (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={
                  collapsed ? 'Expand navigation' : 'Collapse navigation'
                }
                aria-expanded={!collapsed}
                title={
                  collapsed
                    ? 'Show navigation labels'
                    : 'Collapse navigation to an icon rail'
                }
                onClick={() => {
                  dragging.current = false
                  change({ ...layout, collapsed: !collapsed })
                }}
              >
                {collapsed ? (
                  <PanelLeftOpen aria-hidden="true" size={15} />
                ) : (
                  <PanelLeftClose aria-hidden="true" size={15} />
                )}
              </Button>
            )}
          </div>
          {navigation}
        </aside>
        {!compact && !collapsed && (
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
      <DockDropZones target={drag.target} panel="navigation" />
    </div>
  )
}
