import { GripVertical } from 'lucide-react'
import { dockEdges, type Edge } from './dockDrag'
import './dockDrag.css'

export function DockDropZones({
  target,
  panel,
}: {
  target: Edge | null
  panel: string
}) {
  if (!target) return null
  return (
    <div className="dock-drop-zones" data-panel={panel}>
      {dockEdges.map((edge) => (
        <div
          key={edge}
          className={`dock-drop-zone dock-drop-${edge}`}
          data-active={edge === target || undefined}
          aria-hidden="true"
        >
          {edge === target && <span>Dock {edge}</span>}
        </div>
      ))}
      <span className="sr-only" role="status">
        Release to dock {panel} {target}. Press Escape to cancel.
      </span>
    </div>
  )
}

const arrowEdges: Record<string, Edge> = {
  ArrowLeft: 'left',
  ArrowRight: 'right',
  ArrowUp: 'top',
  ArrowDown: 'bottom',
}

/** Small drag handle; keyboard users focus it and press an arrow key to dock. */
export function DockGrip({
  panel,
  value,
  onChange,
}: {
  panel: string
  value: Edge
  onChange: (edge: Edge) => void
}) {
  return (
    <span
      role="button"
      tabIndex={0}
      className="dock-grip-handle"
      aria-label={`Move ${panel}, docked ${value}`}
      aria-keyshortcuts="ArrowLeft ArrowRight ArrowUp ArrowDown"
      title="Drag to dock on another edge, or focus and press an arrow key"
      onKeyDown={(event) => {
        const edge = arrowEdges[event.key]
        if (!edge) return
        event.preventDefault()
        if (edge !== value) onChange(edge)
      }}
    >
      <GripVertical aria-hidden="true" size={14} />
    </span>
  )
}
