// LifeGather service worker: lets the app be installed and shows an offline
// notice. It stores only the notice page and its icon, never the app's HTML,
// API, sign-in, file or chat responses, so personal records never land in the
// browser's cache and every release still loads from the server.
//
// Android's "Share to LifeGather" posts files to /share-target. The worker keeps
// them in memory only, for a few minutes, until the signed-in page claims them
// once and saves them through the normal upload; nothing is written to storage.
const CACHE = 'lifegather-shell-v1'
const OFFLINE_URL = '/offline.html'
const SHELL = [OFFLINE_URL, '/icons/lifegather-192.png']
const SERVER_ONLY = /^\/(?:api|auth|internal|mcp|health)(?:\/|$)/
const SHARE_PATH = '/share-target'
const SHARE_LIMIT = 10
const SHARE_LIFETIME = 5 * 60 * 1000
const shared = new Map()

function shareId() {
  const bytes = new Uint8Array(16)
  self.crypto.getRandomValues(bytes)
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join(
    '',
  )
}

function appUrl(path) {
  return new URL(path, self.location.origin).href
}

async function receiveShare(request) {
  let files = []
  try {
    const form = await request.formData()
    files = form.getAll('files').filter((item) => typeof item !== 'string')
  } catch {
    files = []
  }
  if (!files.length) return Response.redirect(appUrl('/?share=empty'), 303)
  const id = shareId()
  shared.set(id, files.slice(0, SHARE_LIMIT))
  setTimeout(() => shared.delete(id), SHARE_LIFETIME)
  const extra = files.length > SHARE_LIMIT ? '&more=1' : ''
  return Response.redirect(appUrl(`/?share=${id}${extra}`), 303)
}

self.addEventListener('message', (event) => {
  const data = event.data
  const port = event.ports && event.ports[0]
  if (!port || !data || data.type !== 'lifegather-share-claim') return
  const files = shared.get(data.id) || []
  shared.delete(data.id)
  port.postMessage({ files })
})

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('lifegather-') && key !== CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (
    request.method === 'POST' &&
    url.origin === self.location.origin &&
    url.pathname === SHARE_PATH
  ) {
    event.respondWith(receiveShare(request))
    return
  }
  if (request.method !== 'GET' || request.mode !== 'navigate') return
  if (url.origin !== self.location.origin || SERVER_ONLY.test(url.pathname))
    return
  // Pages always come from the network; the cache only answers when it fails.
  event.respondWith(
    fetch(request).catch(() =>
      caches
        .match(OFFLINE_URL)
        .then((response) => response || Response.error()),
    ),
  )
})
