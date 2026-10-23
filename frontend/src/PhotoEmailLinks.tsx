import { useEffect, useState } from 'react'
import { Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'

type EmailLink = { source_id: string; filename: string }

// Saved emails a photo was imported from as an attachment. Most photos have
// none, so nothing renders unless a link exists. Key it by photo to reset.
export function PhotoEmailLinks({
  photoId,
  disabled,
  onOpenSource,
}: {
  photoId: string
  disabled: boolean
  onOpenSource: (id: string) => void
}) {
  const [items, setItems] = useState<EmailLink[]>([])
  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/photos/${encodeURIComponent(photoId)}/email-sources`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('failed')
        return response.json()
      })
      .then((page: { items?: unknown }) => {
        if (controller.signal.aborted || !Array.isArray(page.items)) return
        setItems(
          page.items.filter(
            (item): item is EmailLink =>
              typeof item?.source_id === 'string' &&
              typeof item?.filename === 'string',
          ),
        )
      })
      .catch(() => undefined)
    return () => controller.abort()
  }, [photoId])
  return items.map((link) => (
    <Button
      key={link.source_id}
      variant="outline"
      disabled={disabled}
      onClick={() => onOpenSource(link.source_id)}
    >
      <Mail aria-hidden="true" size={14} />
      Open the email this photo came from
    </Button>
  ))
}
