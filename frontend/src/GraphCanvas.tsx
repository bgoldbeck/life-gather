import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { GraphData, GraphFact } from './graphTypes'

export function GraphCanvas({
  graph,
  onFocus,
  onInspect,
}: {
  graph: GraphData
  onFocus: (id: string) => void
  onInspect: (fact: GraphFact) => void
}) {
  const [zoom, setZoom] = useState(1)
  const others = graph.nodes.filter((n) => n.id !== graph.entity.id)
  const points = new Map(
    graph.nodes.map((node) => {
      const i = others.findIndex((n) => n.id === node.id)
      const angle = (2 * Math.PI * i) / Math.max(1, others.length)
      return [
        node.id,
        node.id === graph.entity.id
          ? { x: 400, y: 260 }
          : { x: 400 + 300 * Math.cos(angle), y: 260 + 190 * Math.sin(angle) },
      ]
    }),
  )
  return (
    <div className="graph-canvas">
      <div className="graph-tools">
        <Button
          variant="outline"
          size="icon"
          onClick={() => setZoom((z) => Math.min(2, z + 0.25))}
          disabled={zoom >= 2}
          aria-label="Zoom in"
        >
          +
        </Button>
        <Button
          variant="outline"
          size="icon"
          onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
          disabled={zoom <= 0.5}
          aria-label="Zoom out"
        >
          −
        </Button>
        <Button variant="outline" onClick={() => setZoom(1)}>
          Reset zoom
        </Button>
      </div>
      <svg
        viewBox={`${400 - 400 / zoom} ${260 - 260 / zoom} ${800 / zoom} ${520 / zoom}`}
        aria-label="Knowledge graph"
        role="group"
      >
        <title>Stored relationships around {graph.entity.name}</title>
        {graph.edges.map((edge) => {
          const a = points.get(edge.subject_id),
            b = points.get(edge.object_id ?? '')
          if (!a || !b) return null
          return (
            <g
              key={edge.id}
              role="button"
              tabIndex={0}
              aria-label={`Inspect connection: ${edge.predicate} (${edge.status})`}
              onClick={() => onInspect(edge)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onInspect(edge)
                }
              }}
            >
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                className="graph-edge"
                strokeDasharray={
                  edge.status === 'inferred'
                    ? '6 5'
                    : edge.status === 'unknown'
                      ? '2 5'
                      : undefined
                }
              />
              <text
                x={(a.x + b.x) / 2}
                y={(a.y + b.y) / 2 - 8}
                className="graph-edge-label"
              >
                {edge.predicate.replaceAll('_', ' ')}
              </text>
            </g>
          )
        })}
        {graph.nodes.map((node) => {
          const point = points.get(node.id)!
          return (
            <g
              key={node.id}
              role="button"
              tabIndex={0}
              aria-label={`Focus ${node.name}`}
              onClick={() => onFocus(node.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onFocus(node.id)
                }
              }}
            >
              <circle
                cx={point.x}
                cy={point.y}
                r={node.id === graph.entity.id ? 32 : 24}
                className={
                  node.id === graph.entity.id
                    ? 'graph-node graph-root'
                    : 'graph-node'
                }
              />
              <text
                x={point.x}
                y={point.y + 48}
                textAnchor="middle"
                className="graph-node-label"
              >
                {node.name.length > 24
                  ? node.name.slice(0, 21) + '…'
                  : node.name}
              </text>
              <title>
                {node.name} — {node.kind}
              </title>
            </g>
          )
        })}
      </svg>
      <p>
        Dashed connections are inferred; dotted connections are unknown. Select
        a connection to inspect its status and evidence.
      </p>
    </div>
  )
}
