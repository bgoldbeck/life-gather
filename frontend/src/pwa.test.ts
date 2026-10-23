import { describe, expect, it, vi } from 'vitest'
import { registerServiceWorker } from './pwa'
import workerSource from '../public/sw.js?raw'

function scopeWith(register: ReturnType<typeof vi.fn> | null, secure = true) {
  return {
    isSecureContext: secure,
    navigator: {
      serviceWorker: register ? { register } : undefined,
    } as unknown as Navigator,
  }
}

describe('registerServiceWorker', () => {
  it('registers the app-wide worker in secure production pages', async () => {
    const register = vi.fn().mockResolvedValue('registration')
    await expect(
      registerServiceWorker(scopeWith(register), true),
    ).resolves.toBe('registration')
    expect(register).toHaveBeenCalledWith('/sw.js', {
      scope: '/',
      updateViaCache: 'none',
    })
  })

  it('skips development builds, insecure pages and browsers without support', async () => {
    const register = vi.fn()
    await expect(
      registerServiceWorker(scopeWith(register), false),
    ).resolves.toBeNull()
    await expect(
      registerServiceWorker(scopeWith(register, false), true),
    ).resolves.toBeNull()
    await expect(
      registerServiceWorker(scopeWith(null), true),
    ).resolves.toBeNull()
    expect(register).not.toHaveBeenCalled()
  })

  it('keeps the app working when registration fails', async () => {
    const register = vi.fn().mockRejectedValue(new Error('blocked'))
    await expect(
      registerServiceWorker(scopeWith(register), true),
    ).resolves.toBeNull()
  })
})

type Listener = (event: Record<string, unknown>) => void

function loadWorker() {
  const listeners: Record<string, Listener> = {}
  const stored: string[][] = []
  const cache = {
    addAll: vi.fn(async (urls: string[]) => void stored.push(urls)),
  }
  const offline = { offline: true }
  const caches = {
    open: vi.fn(async () => cache),
    keys: vi.fn(async () => [
      'lifegather-shell-v0',
      'lifegather-shell-v1',
      'other-app',
    ]),
    delete: vi.fn(async () => true),
    match: vi.fn(async () => offline),
  }
  const self = {
    location: { origin: 'https://life.example' },
    addEventListener: (type: string, listener: Listener) =>
      (listeners[type] = listener),
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
    crypto: globalThis.crypto,
  }
  const fetch = vi.fn()
  const Response = {
    error: () => null,
    redirect: (url: string, status: number) => ({ url, status }),
  }
  const globals = { self, caches, fetch, URL, Response }
  new Function(...Object.keys(globals), workerSource)(...Object.values(globals))
  return { listeners, stored, caches, fetch, offline }
}

function fetchEvent(
  url: string,
  init: { method?: string; mode?: string; form?: FormData } = {},
) {
  const respondWith = vi.fn()
  const request = {
    url,
    method: init.method ?? 'GET',
    mode: init.mode ?? 'navigate',
    formData: async () => init.form ?? new FormData(),
  }
  return { event: { request, respondWith }, respondWith }
}

describe('service worker', () => {
  it('stores only the offline notice and its icon', async () => {
    const worker = loadWorker()
    let pending: Promise<unknown> = Promise.resolve()
    worker.listeners.install({
      waitUntil: (p: Promise<unknown>) => (pending = p),
    })
    await pending
    expect(worker.stored).toEqual([
      ['/offline.html', '/icons/lifegather-192.png'],
    ])
  })

  it('removes only its own older caches when a new worker activates', async () => {
    const worker = loadWorker()
    let pending: Promise<unknown> = Promise.resolve()
    worker.listeners.activate({
      waitUntil: (p: Promise<unknown>) => (pending = p),
    })
    await pending
    expect(worker.caches.delete).toHaveBeenCalledTimes(1)
    expect(worker.caches.delete).toHaveBeenCalledWith('lifegather-shell-v0')
  })

  it.each([
    ['/api/assets', {}],
    ['/auth/google/callback?code=x', {}],
    ['/internal/scans', {}],
    ['/mcp', {}],
    ['/assets/index-AbC123xy.js', { mode: 'no-cors' }],
    ['/', { method: 'POST' }],
  ])('leaves %s to the browser and server', (path, init) => {
    const worker = loadWorker()
    const { event, respondWith } = fetchEvent(
      `https://life.example${path}`,
      init,
    )
    worker.listeners.fetch(event)
    expect(respondWith).not.toHaveBeenCalled()
  })

  it('ignores other sites', () => {
    const worker = loadWorker()
    const { event, respondWith } = fetchEvent('https://elsewhere.example/')
    worker.listeners.fetch(event)
    expect(respondWith).not.toHaveBeenCalled()
  })

  it('loads pages from the network and never caches them', async () => {
    const worker = loadWorker()
    const page = { page: true }
    worker.fetch.mockResolvedValue(page)
    const { event, respondWith } = fetchEvent('https://life.example/assets/42')
    worker.listeners.fetch(event)
    await expect(respondWith.mock.calls[0][0]).resolves.toBe(page)
    expect(worker.caches.open).not.toHaveBeenCalled()
  })

  it('shows the offline notice when the server cannot be reached', async () => {
    const worker = loadWorker()
    worker.fetch.mockRejectedValue(new TypeError('offline'))
    const { event, respondWith } = fetchEvent('https://life.example/')
    worker.listeners.fetch(event)
    await expect(respondWith.mock.calls[0][0]).resolves.toBe(worker.offline)
    expect(worker.caches.match).toHaveBeenCalledWith('/offline.html')
  })
})

describe('share target', () => {
  type Redirect = { url: string; status: number }
  async function share(worker: ReturnType<typeof loadWorker>, files: File[]) {
    const form = new FormData()
    form.append('title', 'not a file')
    for (const file of files) form.append('files', file)
    const { event, respondWith } = fetchEvent(
      'https://life.example/share-target',
      { method: 'POST', form },
    )
    worker.listeners.fetch(event)
    return (await respondWith.mock.calls[0][0]) as Redirect
  }
  function claim(worker: ReturnType<typeof loadWorker>, id: string) {
    const postMessage = vi.fn()
    worker.listeners.message({
      data: { type: 'lifegather-share-claim', id },
      ports: [{ postMessage }],
    })
    return postMessage.mock.calls[0][0] as { files: File[] }
  }
  const receipt = () =>
    new File(['synthetic'], 'Synthetic receipt.jpg', { type: 'image/jpeg' })

  it('keeps shared files in memory and hands them over exactly once', async () => {
    const worker = loadWorker()
    const redirect = await share(worker, [receipt()])
    expect(redirect.status).toBe(303)
    const id = new URL(redirect.url).searchParams.get('share')!
    expect(id).toMatch(/^[0-9a-f]{32}$/)
    expect(claim(worker, 'f'.repeat(32)).files).toEqual([])
    const first = claim(worker, id).files
    expect(first.map((file) => file.name)).toEqual(['Synthetic receipt.jpg'])
    expect(claim(worker, id).files).toEqual([])
    // Nothing shared is ever written to the browser's storage.
    expect(worker.caches.open).not.toHaveBeenCalled()
  })

  it('reports an empty share and keeps only the first ten files', async () => {
    const worker = loadWorker()
    expect((await share(worker, [])).url).toBe(
      'https://life.example/?share=empty',
    )
    const many = Array.from({ length: 12 }, receipt)
    const redirect = new URL((await share(loadWorker(), many)).url)
    expect(redirect.searchParams.get('more')).toBe('1')
  })

  it('ignores shares posted to other sites and stray messages', () => {
    const worker = loadWorker()
    const { event, respondWith } = fetchEvent(
      'https://elsewhere.example/share-target',
      { method: 'POST' },
    )
    worker.listeners.fetch(event)
    expect(respondWith).not.toHaveBeenCalled()
    expect(() =>
      worker.listeners.message({ data: { type: 'other' }, ports: [] }),
    ).not.toThrow()
  })
})
