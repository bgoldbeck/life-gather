import { useEffect, useState } from 'react'
import { Boxes } from 'lucide-react'
import { Button } from '@/components/ui/button'

type Linked = { id: string; name: string }

export function PhotoAssetLinks({
  photoId,
  revision,
  onOpenAsset,
}: {
  photoId: string
  // Reload after the photo's links change.
  revision: number
  onOpenAsset: (id: string) => void
}) {
  const [items, setItems] = useState<Linked[] | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/photos/${encodeURIComponent(photoId)}/assets`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('failed')
        return response.json()
      })
      .then((page: { items: Linked[] }) => {
        if (!controller.signal.aborted) setItems(page.items)
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError('Unable to load the assets this photo belongs to.')
      })
    return () => controller.abort()
  }, [photoId, revision])
  if (error) return <p role="alert">{error}</p>
  if (!items) return null
  return (
    <div className="photo-assets" aria-label="Attached to">
      <strong>Attached to</strong>
      {items.length ? (
        <ul>
          {items.map((asset) => (
            <li key={asset.id}>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onOpenAsset(asset.id)}
              >
                <Boxes aria-hidden="true" size={14} />
                Open {asset.name}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p>Not attached to an asset yet.</p>
      )}
    </div>
  )
}
