import { useCallback, useEffect, useState } from 'react'

export type Gallery = {
  id: string
  title: string
  event_on: string | null
  photo_count: number
  cover_photo_id: string | null
  updated_at: number
}
export type GalleryRequest = (path: string, init?: RequestInit) => Promise<any>
export type SavedPhoto = { id: string; filename: string }

// Pages through every saved photo; an account holds at most 200.
const MAX_PAGES = 10
export const MAX_ADD = 50

export function galleryDate(value: string | null) {
  if (!value) return ''
  const [year, month, day] = value.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(
    undefined,
    { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' },
  )
}

export function photoCount(count: number) {
  return count === 1 ? '1 photo' : `${count} photos`
}

export function useGalleries(request: GalleryRequest, enabled: boolean) {
  const [items, setItems] = useState<Gallery[]>([])
  const [error, setError] = useState('')
  const fetchAll = useCallback(
    () =>
      enabled
        ? request('photo-galleries').then(
            (page: { items?: Gallery[] }) => page.items ?? [],
          )
        : Promise.resolve([] as Gallery[]),
    [request, enabled],
  )
  const reload = useCallback(async () => {
    try {
      setItems(await fetchAll())
      setError('')
    } catch {
      setError('Unable to load galleries. Reopen Photos to retry.')
    }
  }, [fetchAll])
  useEffect(() => {
    let alive = true
    fetchAll()
      .then((found) => {
        if (alive) setItems(found)
      })
      .catch(() => {
        if (alive) setError('Unable to load galleries. Reopen Photos to retry.')
      })
    return () => {
      alive = false
    }
  }, [fetchAll])
  return { items, error, reload }
}

export async function allPhotos(request: GalleryRequest, galleryId = '') {
  const found: SavedPhoto[] = []
  let cursor = ''
  for (let page = 0; page < MAX_PAGES; page++) {
    const result = await request(
      `photos?gallery_id=${encodeURIComponent(galleryId)}&cursor=${cursor}`,
    )
    found.push(...result.items)
    if (!result.next_cursor) break
    cursor = result.next_cursor
  }
  return found
}
