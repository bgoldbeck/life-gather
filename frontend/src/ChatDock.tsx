import { useState, type ReactNode } from 'react'
import './chatDock.css'

type Edge = 'bottom' | 'top' | 'left' | 'right'
type Layout = { edge: Edge; collapsed: boolean }
const edges: Edge[] = ['bottom', 'top', 'left', 'right']

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
      return data
  } catch {
    /* Storage may be unavailable. */
  }
  return { edge: 'bottom', collapsed: false }
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
      className={`workspace-body dock-${layout.edge} ${layout.collapsed ? 'dock-collapsed' : ''}`}
    >
      {page}
      <section className="assistant-dock" aria-label="LifeGather assistant">
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
