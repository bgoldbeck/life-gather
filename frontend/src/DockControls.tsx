import { PanelBottom, PanelLeft, PanelRight, PanelTop } from 'lucide-react'
import { dockEdges, type Edge } from './dockDrag'
import './dockDrag.css'

const icons = {
  left: PanelLeft,
  right: PanelRight,
  top: PanelTop,
  bottom: PanelBottom,
}

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

export function DockEdgeButtons({
  panel,
  value,
  title,
  onChange,
}: {
  panel: string
  value: Edge
  title?: string
  onChange: (edge: Edge) => void
}) {
  return (
    <div
      className="dock-edge-buttons"
      role="group"
      aria-label={`${panel[0].toUpperCase() + panel.slice(1)} dock position`}
      title={title}
    >
      {dockEdges.map((edge) => {
        const Icon = icons[edge]
        return (
          <button
            key={edge}
            type="button"
            aria-label={`Dock ${panel} ${edge}`}
            aria-pressed={value === edge}
            title={`Dock ${edge}`}
            onClick={() => onChange(edge)}
          >
            <Icon aria-hidden="true" size={14} />
          </button>
        )
      })}
    </div>
  )
}
