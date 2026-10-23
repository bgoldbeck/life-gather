// Helpers for Android's "Share to LifeGather"; see SharedFiles.tsx.

const MAX_BYTES = 8 * 1024 * 1024
const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const PHOTO_EXTENSIONS = /\.(?:jpe?g|png|webp)$/i
const DOCUMENT_EXTENSIONS = /\.(?:pdf|docx|xlsx|txt|md|csv)$/i

export type ShareRequest = { id: string; more: boolean }

export type Kind = 'photo' | 'document' | 'unsupported' | 'too-large'

export function readShareRequest(search: string): ShareRequest | null {
  const params = new URLSearchParams(search)
  const id = params.get('share')
  if (!id || !/^(?:[0-9a-f]{32}|unavailable|empty)$/.test(id)) return null
  return { id, more: params.get('more') === '1' }
}

export function fileKind(file: File): Kind {
  if (file.size > MAX_BYTES) return 'too-large'
  if (PHOTO_TYPES.includes(file.type) || PHOTO_EXTENSIONS.test(file.name))
    return 'photo'
  if (DOCUMENT_EXTENSIONS.test(file.name)) return 'document'
  return 'unsupported'
}

type Workers = Pick<ServiceWorkerContainer, 'ready'>

// Asks the service worker for the files of one share. They are handed over
// once and removed from the worker, so a second claim returns nothing.
export async function claimSharedFiles(
  id: string,
  workers: Workers | undefined = navigator.serviceWorker,
  timeout = 5000,
): Promise<File[]> {
  if (!workers) return []
  const registration = await Promise.race([
    workers.ready,
    new Promise<null>((resolve) => setTimeout(() => resolve(null), timeout)),
  ])
  const worker = registration?.active
  if (!worker) return []
  return new Promise<File[]>((resolve) => {
    const channel = new MessageChannel()
    const timer = setTimeout(() => resolve([]), timeout)
    channel.port1.onmessage = (event: MessageEvent<{ files?: File[] }>) => {
      clearTimeout(timer)
      const files = event.data?.files
      resolve(Array.isArray(files) ? files : [])
    }
    worker.postMessage({ type: 'lifegather-share-claim', id }, [channel.port2])
  })
}

const claims = new Map<string, Promise<File[]>>()

// Claims a share as soon as the page loads, before sign-in finishes: the browser
// may stop an idle service worker within seconds, taking the files with it.
// The files then wait in this page's memory only, never in storage.
export function claimShareOnce(id: string): Promise<File[]> {
  if (!/^[0-9a-f]{32}$/.test(id)) return Promise.resolve([])
  let claim = claims.get(id)
  if (!claim) {
    claim = claimSharedFiles(id).catch(() => [])
    claims.set(id, claim)
  }
  return claim
}
