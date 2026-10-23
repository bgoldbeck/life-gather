import { expect, test } from '@playwright/test'

import { openView, secondURL, signIn } from './support.ts'

// Home screen install: the manifest is valid, the service worker activates and
// stores only the offline notice, even after a signed-in session has loaded
// private records.

test('installs without storing anything private', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: secondURL })
  const page = await context.newPage()
  await signIn(page, secondURL)

  const manifest = await page.evaluate(async () => {
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]')
    return (await fetch(link!.href)).json()
  })
  expect(manifest).toMatchObject({ name: 'LifeGather', display: 'standalone' })

  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  expect(await page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(
    true,
  )

  // Load pages that fetch private records while the worker controls the page.
  await openView(page, 'Assets')
  await openView(page, 'Settings')

  const stored = await page.evaluate(async () => {
    const urls: string[] = []
    for (const name of await caches.keys()) {
      for (const request of await (await caches.open(name)).keys())
        urls.push(`${name} ${new URL(request.url).pathname}`)
    }
    return urls.sort()
  })
  expect(stored).toEqual([
    'lifegather-shell-v1 /icons/lifegather-192.png',
    'lifegather-shell-v1 /offline.html',
  ])

  // Chromium's offline emulation doesn't reach the worker's own requests, so
  // check the stored notice directly; src/pwa.test.ts covers the fallback.
  const notice = await page.evaluate(async () =>
    (await caches.match('/offline.html'))?.text(),
  )
  expect(notice).toContain("Can't reach your LifeGather server")
  await context.close()
})
