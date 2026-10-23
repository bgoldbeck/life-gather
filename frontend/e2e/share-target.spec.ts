/// <reference lib="dom" />

import { readFile } from 'node:fs/promises'
import path from 'node:path'

import { expect, test, type Page } from '@playwright/test'

import { account, secondURL, signIn } from './support.ts'

// Share to LifeGather (Android): the service worker receives a share posted to
// /share-target, keeps the files in memory only, and the signed-in page saves
// them through the normal uploads. Nothing shared lands in browser storage.

const fixture = (name: string) =>
  readFile(path.join(import.meta.dirname, 'fixtures', name))

type Shared = { name: string; type: string; bytes: number[] }

// Android submits the share as a multipart form navigation; do the same.
async function share(page: Page, files: Shared[]) {
  await page.evaluate((shared) => {
    const form = document.createElement('form')
    form.method = 'post'
    form.enctype = 'multipart/form-data'
    form.action = '/share-target'
    const input = document.createElement('input')
    input.type = 'file'
    input.name = 'files'
    input.multiple = true
    const transfer = new DataTransfer()
    for (const file of shared)
      transfer.items.add(
        new File([new Uint8Array(file.bytes)], file.name, { type: file.type }),
      )
    input.files = transfer.files
    form.append(input)
    document.body.append(form)
    form.submit()
  }, files)
}

test('saves files shared from another app without storing them in the browser', async ({
  browser,
}) => {
  const context = await browser.newContext({ baseURL: secondURL })
  const page = await context.newPage()
  await signIn(page, secondURL)
  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()

  const files = [
    {
      name: 'Shared synthetic lamp.png',
      type: 'image/png',
      bytes: [...(await fixture('synthetic-lamp.png'))],
    },
    {
      name: 'Shared synthetic receipt.txt',
      type: 'text/plain',
      bytes: [...(await fixture('synthetic-receipt.txt'))],
    },
  ]
  await share(page, files)

  const panel = page.getByRole('region', { name: 'Shared to LifeGather' })
  await expect(
    panel.getByText('Shared synthetic lamp.png', { exact: true }),
  ).toBeVisible()
  await expect(
    panel.getByText('Shared synthetic receipt.txt', { exact: true }),
  ).toBeVisible()
  expect(new URL(page.url()).search).toBe('')
  await panel
    .getByLabel('Photo purpose for Shared synthetic lamp.png')
    .selectOption('receipt')
  await panel.getByRole('button', { name: 'Save 2 files' }).click()
  await expect(panel.getByText('Saved', { exact: true })).toHaveCount(2)

  // Photos opens; after the restore in core-journeys the same lamp bytes are
  // already saved, so the upload matches that photo instead of adding one.
  await panel.getByRole('button', { name: 'Open Photos' }).click()
  await expect(
    page.getByRole('heading', { name: 'Private photos' }),
  ).toBeVisible()

  const stored = await page.evaluate(async () => {
    const urls: string[] = []
    for (const name of await caches.keys())
      for (const request of await (await caches.open(name)).keys())
        urls.push(new URL(request.url).pathname)
    const databases = (await indexedDB.databases()).map((db) => db.name)
    return { urls: urls.sort(), databases }
  })
  expect(stored).toEqual({
    urls: ['/icons/lifegather-192.png', '/offline.html'],
    databases: [],
  })

  // The worker handed the files over once; reopening the address finds nothing.
  await page.goto('/?share=' + 'f'.repeat(32))
  await expect(
    page.getByText(/shared files are no longer available/),
  ).toBeVisible()
  await context.close()
})

test('keeps a share while the person signs in with a password', async ({
  browser,
}) => {
  const context = await browser.newContext({ baseURL: secondURL })
  const page = await context.newPage()
  await page.goto('/')
  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await share(page, [
    {
      name: 'Signed-out synthetic receipt.txt',
      type: 'text/plain',
      bytes: [...(await fixture('synthetic-receipt.txt'))],
    },
  ])
  await page.getByRole('textbox', { name: 'Email' }).fill(account.email)
  await page.getByRole('textbox', { name: 'Password' }).fill(account.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  const panel = page.getByRole('region', { name: 'Shared to LifeGather' })
  await expect(
    panel.getByText('Signed-out synthetic receipt.txt', { exact: true }),
  ).toBeVisible()
  await panel.getByRole('button', { name: 'Discard' }).click()
  await expect(panel).toHaveCount(0)
  await context.close()
})
