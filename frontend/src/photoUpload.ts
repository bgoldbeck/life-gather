// Sends one photo's original bytes to /api/photos with upload progress.
// fetch cannot report upload progress, so this uses XMLHttpRequest. The server
// stores a photo once per content hash, so sending the same file again after a
// lost response or a Cancel never makes a second copy.

export const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
export const PHOTO_ACCEPT = PHOTO_TYPES.join(',')
export const MAX_PHOTO_BYTES = 8 * 1024 * 1024

export type PhotoUploadResult<T> =
  | { kind: 'saved'; photo: T }
  | { kind: 'rejected'; status: number }
  | { kind: 'unknown' }
  | { kind: 'cancelled' }

export function photoFileProblem(file: File): string {
  if (
    !file.size ||
    file.size > MAX_PHOTO_BYTES ||
    (file.type && !PHOTO_TYPES.includes(file.type))
  )
    return 'Choose a nonempty JPEG, PNG or WebP no larger than 8 MiB.'
  return ''
}

export function sendPhoto<T>({
  url,
  file,
  csrfToken,
  signal,
  onProgress,
}: {
  url: string
  file: File
  csrfToken: string
  signal: AbortSignal
  onProgress: (percent: number) => void
}): Promise<PhotoUploadResult<T>> {
  return new Promise((resolve) => {
    if (signal.aborted) return resolve({ kind: 'cancelled' })
    const request = new XMLHttpRequest()
    const abort = () => request.abort()
    const finish = (result: PhotoUploadResult<T>) => {
      signal.removeEventListener('abort', abort)
      resolve(result)
    }
    request.open('POST', url)
    request.withCredentials = true
    request.setRequestHeader('Content-Type', 'application/octet-stream')
    request.setRequestHeader('X-CSRF-Token', csrfToken)
    request.setRequestHeader('X-File-Name', encodeURIComponent(file.name))
    request.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total)
        onProgress(
          Math.min(100, Math.round((event.loaded / event.total) * 100)),
        )
    }
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          finish({ kind: 'saved', photo: JSON.parse(request.responseText) })
        } catch {
          finish({ kind: 'unknown' })
        }
      } else if (request.status >= 400 && request.status < 500)
        finish({ kind: 'rejected', status: request.status })
      else finish({ kind: 'unknown' })
    }
    request.onerror = () => finish({ kind: 'unknown' })
    request.ontimeout = () => finish({ kind: 'unknown' })
    request.onabort = () => finish({ kind: 'cancelled' })
    signal.addEventListener('abort', abort)
    request.send(file)
  })
}
