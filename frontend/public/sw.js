// LifeGather service worker: lets the app be installed and shows an offline
// notice. It stores only the notice page and its icon, never the app's HTML,
// API, sign-in, file or chat responses, so personal records never land in the
// browser's cache and every release still loads from the server.
const CACHE = 'lifegather-shell-v1'
const OFFLINE_URL = '/offline.html'
const SHELL = [OFFLINE_URL, '/icons/lifegather-192.png']
const SERVER_ONLY = /^\/(?:api|auth|internal|mcp|health)(?:\/|$)/

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
  if (request.method !== 'GET' || request.mode !== 'navigate') return
  const url = new URL(request.url)
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
