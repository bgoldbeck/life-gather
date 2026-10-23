import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { SharedFiles } from './SharedFiles'
import {
  androidBridge,
  claimAndroidFiles,
  claimSharedFiles,
  fileKind,
  readShareRequest,
} from './shareTarget'

afterEach(() => vi.unstubAllGlobals())

const ID = 'a'.repeat(32)
const receipt = () =>
  new File(['synthetic receipt image'], 'Synthetic receipt.jpg', {
    type: 'image/jpeg',
  })
const manual = () =>
  new File(['%PDF synthetic'], 'Synthetic manual.pdf', {
    type: 'application/pdf',
  })

function mount(files: File[], id = ID, more = false) {
  const claim = vi.fn(async () => files)
  const onClose = vi.fn()
  const onOpenPhotos = vi.fn()
  const onOpenDocuments = vi.fn()
  render(
    <SharedFiles
      share={{ id, more }}
      csrfToken="csrf"
      onClose={onClose}
      onOpenPhotos={onOpenPhotos}
      onOpenDocuments={onOpenDocuments}
      claim={claim}
    />,
  )
  return { claim, onClose, onOpenPhotos, onOpenDocuments }
}

it('reads only well-formed share addresses', () => {
  expect(readShareRequest(`?share=${ID}&more=1`)).toEqual({
    id: ID,
    more: true,
  })
  expect(readShareRequest('?share=unavailable')).toEqual({
    id: 'unavailable',
    more: false,
  })
  expect(readShareRequest('?share=../api')).toBeNull()
  expect(readShareRequest('?mailbox=connected')).toBeNull()
})

it('sorts shared files into photos, documents and files it cannot save', () => {
  expect(fileKind(receipt())).toBe('photo')
  expect(fileKind(manual())).toBe('document')
  expect(fileKind(new File(['x'], 'clip.mp4', { type: 'video/mp4' }))).toBe(
    'unsupported',
  )
  const large = new File(['x'], 'big.jpg', { type: 'image/jpeg' })
  Object.defineProperty(large, 'size', { value: 9 * 1024 * 1024 })
  expect(fileKind(large)).toBe('too-large')
})

it('saves nothing until asked, then uploads each file through the normal upload', async () => {
  const fetcher = vi.fn(
    async () => new Response(JSON.stringify({ id: 'saved' }), { status: 201 }),
  )
  vi.stubGlobal('fetch', fetcher)
  const { claim, onOpenPhotos, onOpenDocuments } = mount([
    receipt(),
    manual(),
    new File(['x'], 'clip.mp4', { type: 'video/mp4' }),
  ])
  const user = userEvent.setup()
  expect(await screen.findByText('Synthetic receipt.jpg')).toBeVisible()
  expect(claim).toHaveBeenCalledWith(ID)
  expect(screen.getByText(/This file type cannot be saved/)).toBeVisible()
  expect(fetcher).not.toHaveBeenCalled()

  await user.selectOptions(
    screen.getByLabelText('Photo purpose for Synthetic receipt.jpg'),
    'receipt',
  )
  await user.click(screen.getByRole('button', { name: 'Save 2 files' }))
  expect(await screen.findAllByText('Saved')).toHaveLength(2)
  expect(fetcher).toHaveBeenCalledTimes(2)
  expect(fetcher).toHaveBeenNthCalledWith(
    1,
    '/api/photos?purpose=receipt',
    expect.objectContaining({
      method: 'POST',
      credentials: 'same-origin',
      headers: expect.objectContaining({
        'X-CSRF-Token': 'csrf',
        'X-File-Name': 'Synthetic%20receipt.jpg',
      }),
    }),
  )
  expect(fetcher).toHaveBeenNthCalledWith(
    2,
    '/api/documents?encoding=utf-8-sig',
    expect.objectContaining({
      headers: expect.objectContaining({ 'Content-Type': 'application/pdf' }),
    }),
  )
  await user.click(screen.getByRole('button', { name: 'Open Photos' }))
  expect(onOpenPhotos).toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: 'Open Documents' }))
  expect(onOpenDocuments).toHaveBeenCalled()
})

it('shows the storage limit message and lets the person retry', async () => {
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          detail:
            "Your account's file storage is full (1 MiB); delete photos or documents to make room",
        }),
        { status: 400 },
      ),
    )
    .mockResolvedValueOnce(new Response('{}', { status: 201 }))
  vi.stubGlobal('fetch', fetcher)
  mount([receipt()])
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Save 1 file' }))
  expect(await screen.findByText(/file storage is full/)).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Save 1 file' }))
  expect(await screen.findByText('Saved')).toBeVisible()
})

it('explains when the shared files are gone and never claims a fallback share', async () => {
  const { claim } = mount([], 'unavailable')
  expect(
    await screen.findByText(/shared files are no longer available/),
  ).toBeVisible()
  expect(claim).not.toHaveBeenCalled()
})

it('closes without saving', async () => {
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  const { onClose } = mount([receipt()], ID, true)
  const user = userEvent.setup()
  expect(await screen.findByText(/first 10 files/)).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Discard' }))
  expect(onClose).toHaveBeenCalled()
  expect(fetcher).not.toHaveBeenCalled()
})

it('claims the files from the active service worker over a private channel', async () => {
  const shared = [receipt()]
  const postMessage = vi.fn(
    (message: { type: string; id: string }, [port]: MessagePort[]) => {
      expect(message).toEqual({ type: 'lifegather-share-claim', id: ID })
      port.postMessage({ files: shared })
    },
  )
  const workers = {
    ready: Promise.resolve({
      active: { postMessage },
    } as unknown as ServiceWorkerRegistration),
  }
  const files = await claimSharedFiles(ID, workers)
  // Node's channel clones jsdom files as plain objects; the browser check in
  // e2e/share-target.spec.ts covers real files.
  expect(files).toHaveLength(1)
  await expect(claimSharedFiles(ID, undefined)).resolves.toEqual([])
})

it('takes shared files from the Android app, only from its own addresses', async () => {
  const sharedFiles = vi.fn(() =>
    JSON.stringify([
      {
        url: `/__lifegather-android/share/${ID}/0`,
        name: 'Synthetic receipt.jpg',
        type: 'image/jpeg',
      },
      { url: 'https://elsewhere.example/file', name: 'x', type: 'image/png' },
      { url: `/__lifegather-android/share/${'b'.repeat(32)}/0`, name: 'y' },
      { url: `/__lifegather-android/share/${ID}/1`, name: '', type: '' },
    ]),
  )
  const fetcher = vi.fn(
    async (_url: string) => new Response('synthetic receipt image'),
  )
  const files = await claimAndroidFiles(
    ID,
    { sharedFiles },
    fetcher as unknown as typeof fetch,
  )
  expect(sharedFiles).toHaveBeenCalledWith(ID)
  expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
    `/__lifegather-android/share/${ID}/0`,
    `/__lifegather-android/share/${ID}/1`,
  ])
  expect(files.map((file) => [file.name, file.type, file.size])).toEqual([
    ['Synthetic receipt.jpg', 'image/jpeg', 23],
    ['Shared file', '', 23],
  ])
  expect(fileKind(files[0])).toBe('photo')
})

it('uses the Android bridge only inside the Android app', () => {
  expect(androidBridge()).toBeUndefined()
  vi.stubGlobal('LifeGatherAndroid', { sharedFiles: () => '[]' })
  expect(androidBridge()).toBeDefined()
})
