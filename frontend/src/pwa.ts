// Registers the service worker that makes LifeGather installable. It only runs
// in production builds served over HTTPS (or localhost), where browsers allow it.
export function registerServiceWorker(
  scope: Pick<Window, 'isSecureContext'> & { navigator: Navigator } = window,
  production: boolean = import.meta.env.PROD,
): Promise<ServiceWorkerRegistration | null> {
  const workers = scope.navigator.serviceWorker
  if (!production || !scope.isSecureContext || !workers)
    return Promise.resolve(null)
  // The app already reloads on its own update notice, so the worker file is
  // always checked against the server instead of the HTTP cache.
  return workers
    .register('/sw.js', { scope: '/', updateViaCache: 'none' })
    .catch(() => null)
}
