import {
  useEffect,
  useRef,
  useState,
  type PointerEvent,
  type RefObject,
} from 'react'

export type Edge = 'left' | 'right' | 'top' | 'bottom'
export const dockEdges: Edge[] = ['left', 'right', 'top', 'bottom']
// Pointer travel before a header press becomes a drag, so clicks stay clicks.
const threshold = 6

export function nearestEdge(rect: DOMRect, x: number, y: number): Edge {
  const distances: [Edge, number][] = [
    ['left', (x - rect.left) / rect.width],
    ['right', (rect.right - x) / rect.width],
    ['top', (y - rect.top) / rect.height],
    ['bottom', (rect.bottom - y) / rect.height],
  ]
  return distances.reduce((best, next) => (next[1] < best[1] ? next : best))[0]
}

/** Drag a panel by its header; drop zones follow the edge nearest the pointer. */
export function useDockDrag(
  area: RefObject<HTMLElement | null>,
  enabled: boolean,
  onDrop: (edge: Edge) => void,
) {
  const [target, setTarget] = useState<Edge | null>(null)
  const press = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const current = useRef<Edge | null>(null)
  function reset() {
    press.current = null
    current.current = null
    setTarget(null)
  }
  useEffect(() => {
    if (!target) return
    const cancel = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      press.current = null
      current.current = null
      setTarget(null)
    }
    window.addEventListener('keydown', cancel)
    return () => window.removeEventListener('keydown', cancel)
  }, [target])
  const handleProps = {
    onPointerDown(event: PointerEvent<HTMLElement>) {
      if (!enabled || event.button !== 0) return
      if (
        (event.target as Element).closest('button, a, input, select, textarea')
      )
        return
      press.current = { x: event.clientX, y: event.clientY, moved: false }
      event.currentTarget.setPointerCapture?.(event.pointerId)
    },
    onPointerMove(event: PointerEvent<HTMLElement>) {
      const start = press.current
      if (!start) return
      if (
        !start.moved &&
        Math.hypot(event.clientX - start.x, event.clientY - start.y) < threshold
      )
        return
      start.moved = true
      const rect = area.current?.getBoundingClientRect()
      if (!rect || rect.width <= 0 || rect.height <= 0) return
      const edge = nearestEdge(rect, event.clientX, event.clientY)
      current.current = edge
      setTarget(edge)
    },
    onPointerUp(event: PointerEvent<HTMLElement>) {
      const edge = current.current
      reset()
      if (event.currentTarget.hasPointerCapture?.(event.pointerId))
        event.currentTarget.releasePointerCapture(event.pointerId)
      if (edge) onDrop(edge)
    },
    onPointerCancel: reset,
  }
  return { target, handleProps }
}
