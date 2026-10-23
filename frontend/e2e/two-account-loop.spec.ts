import { readFile } from 'node:fs/promises'
import path from 'node:path'

import { expect, test, type Page } from '@playwright/test'

import {
  account,
  openView,
  restartInstallation,
  secondAccount,
  sharedPort,
  sharedURL,
  signIn,
} from './support.ts'

// The Phase 3 loop for two accounts in one installation: add, evidence,
// recall, correction, restart and backup/restore, checking at each step that
// nothing crosses between the accounts. Each account has its own browser
// context, as on two computers. All records are synthetic.
test.describe.configure({ mode: 'serial' })

const fixtures = path.join(import.meta.dirname, 'fixtures')
const photoFile = path.join(fixtures, 'synthetic-lamp.png')
const receiptFile = path.join(fixtures, 'synthetic-receipt.txt')

// Words that appear only in one account's records.
const first = {
  asset: 'Walnut bookshelf',
  manufacturer: 'Example Woodworks',
  photo: 'synthetic-lamp.png',
}
const second = {
  asset: 'Cedar garden bench',
  document: 'synthetic-receipt.txt',
  store: 'Example Hardware Store',
}
// Both accounts own an item with this name.
const shared = 'Cordless drill'

let one: Page
let two: Page
let firstArchive = ''

test.beforeAll(async ({ browser }) => {
  one = await (await browser.newContext({ baseURL: sharedURL })).newPage()
  two = await (await browser.newContext({ baseURL: sharedURL })).newPage()
})

test.afterAll(async () => {
  await one.context().close()
  await two.context().close()
})

async function addAsset(page: Page, name: string, manufacturer = '') {
  await openView(page, 'Assets')
  const assets = page.getByRole('region', { name: 'Your assets' })
  await assets.getByRole('button', { name: 'Add asset' }).click()
  const form = page.getByRole('region', { name: 'Add asset manually' })
  await form.getByLabel('Asset name').fill(name)
  if (manufacturer) await form.getByLabel('Manufacturer').fill(manufacturer)
  await form.getByLabel('I currently own this item').check()
  await form.getByRole('button', { name: 'Save asset' }).click()
  await expect(
    assets.getByText(`${name} saved with your stated ownership.`),
  ).toBeVisible()
  await expect(form.getByLabel('Possible duplicate assets')).toHaveCount(0)
}

async function assetNames(page: Page) {
  await openView(page, 'Assets')
  const list = page.getByRole('region', { name: 'Your assets' })
  // Sold items are historical records; list them too.
  await list.getByLabel('Include historical records').check()
  await expect(
    list.getByRole('button', { name: shared, exact: true }),
  ).toHaveCount(1)
  return list
}

async function openAsset(page: Page, name: string) {
  const list = await assetNames(page)
  await list.getByRole('button', { name, exact: true }).click()
  const details = page.getByRole('region', { name: 'Asset details' })
  await expect(details.getByRole('heading', { name })).toBeVisible()
  return details
}

async function search(page: Page, words: string) {
  const box = page.getByRole('searchbox', {
    name: 'Search assets, photos, documents and sources',
  })
  await box.fill(words)
  await box.press('Enter')
  return page.getByRole('region', { name: 'Search results' })
}

async function expectFound(page: Page, words: string, record: RegExp) {
  const results = await search(page, words)
  await expect(
    results.getByRole('button', { name: record }).first(),
  ).toBeVisible()
}

async function expectNothing(page: Page, words: string) {
  const results = await search(page, words)
  await expect(results).toBeVisible()
  await expect(results.getByRole('button')).toHaveCount(0)
}

async function recallStaysSeparate() {
  await expectFound(one, first.asset, new RegExp(first.asset))
  await expectFound(one, first.photo, new RegExp(first.photo))
  await expectNothing(one, second.asset)
  await expectNothing(one, second.store)

  await expectFound(two, second.asset, new RegExp(second.asset))
  await expectFound(two, second.store, new RegExp(second.document))
  await expectNothing(two, first.asset)
  await expectNothing(two, first.manufacturer)
  await expectNothing(two, first.photo)
}

async function download(page: Page, archive: boolean) {
  await openView(page, 'Settings')
  const card = page.getByRole('region', { name: 'Download your records' })
  const zip = card.getByLabel('Include original photos and documents (ZIP)')
  if (archive) await zip.check()
  else await zip.uncheck()
  const started = page.waitForEvent('download')
  await card
    .getByRole('button', {
      name: archive ? 'Download archive (ZIP)' : 'Download records (JSON)',
    })
    .click()
  const file = test
    .info()
    .outputPath(
      `${page === one ? 'first' : 'second'}-${archive ? 'archive.zip' : 'records.json'}`,
    )
  await (await started).saveAs(file)
  return file
}

async function restore(page: Page, file: string) {
  await openView(page, 'Settings')
  const card = page.getByRole('region', { name: 'Restore your records' })
  await card.getByLabel('Personal archive (ZIP)').setInputFiles(file)
  await card.getByLabel("Add this archive's records to my account").check()
  await card.getByRole('button', { name: 'Restore archive' }).click()
  return card
}

test('two accounts sign in to one installation', async () => {
  await signIn(one, sharedURL, account)
  await signIn(two, sharedURL, secondAccount)
  await expect(one.getByRole('banner')).toContainText(account.name)
  await expect(two.getByRole('banner')).toContainText(secondAccount.name)
})

test('each account adds its own assets; a shared name is not a duplicate', async () => {
  await addAsset(one, first.asset, first.manufacturer)
  await addAsset(one, shared)
  await addAsset(two, second.asset)
  // The same name in another account is neither offered for linking nor merged.
  await addAsset(two, shared)

  const mine = await assetNames(one)
  await expect(
    mine.getByRole('button', { name: first.asset, exact: true }),
  ).toBeVisible()
  await expect(
    mine.getByRole('button', { name: second.asset, exact: true }),
  ).toHaveCount(0)
  const theirs = await assetNames(two)
  await expect(
    theirs.getByRole('button', { name: second.asset, exact: true }),
  ).toBeVisible()
  await expect(
    theirs.getByRole('button', { name: first.asset, exact: true }),
  ).toHaveCount(0)
})

test('evidence added in one account stays out of the other', async () => {
  const details = await openAsset(one, first.asset)
  const media = details.getByRole('region', { name: 'Photos and documents' })
  await media.getByLabel('Photo file').setInputFiles(photoFile)
  await media.getByLabel('Photo purpose').selectOption('Receipt')
  await media
    .getByRole('button', { name: 'Upload privately to this item' })
    .click()
  await expect(
    media.getByRole('button', { name: new RegExp(first.photo) }),
  ).toBeVisible()

  await openView(two, 'Documents')
  await two.getByLabel('Document file').setInputFiles(receiptFile)
  await two.getByRole('button', { name: 'Upload document' }).click()
  const review = two.getByRole('region', { name: 'Document review' })
  await expect(review.getByLabel('Reviewed text')).toHaveValue(
    new RegExp(second.store),
  )
  await review
    .getByRole('button', { name: 'Save reviewed text to memory' })
    .click()
  await expect(
    two.getByRole('button', { name: new RegExp(second.document) }),
  ).not.toContainText('Needs text review')

  await openView(two, 'Photos')
  await expect(
    two.getByRole('region', { name: 'Private photos' }),
  ).toBeVisible()
  await expect(
    two.getByRole('button', { name: new RegExp(first.photo) }),
  ).toHaveCount(0)
  await openView(one, 'Documents')
  await expect(one.getByLabel('Document file')).toBeVisible()
  await expect(
    one.getByRole('button', { name: new RegExp(second.document) }),
  ).toHaveCount(0)
})

test('recall finds only the signed-in account’s records', async () => {
  await recallStaysSeparate()

  // Another account's record answers exactly like an ID that never existed,
  // so a request does not even reveal that the record exists.
  const assets = await (await one.request.get('/api/assets')).json()
  const assetId = assets.items.find(
    (item: { name: string }) => item.name === first.asset,
  ).id
  const photoId = (await (await one.request.get('/api/photos')).json()).items[0]
    .id
  const documentId = (await (await two.request.get('/api/documents')).json())
    .items[0].id
  const probes: [Page, Page, string][] = [
    [one, two, `/api/assets/${assetId}`],
    [one, two, `/api/assets/${assetId}/purchases`],
    [one, two, `/api/photos/${photoId}`],
    [one, two, `/api/photos/${photoId}/assets`],
    [one, two, `/api/photos/${photoId}/preview`],
    [one, two, `/api/photos/${photoId}/original`],
    [two, one, `/api/documents/${documentId}`],
    [two, one, `/api/documents/${documentId}/original`],
  ]
  const missing = '00000000-0000-4000-8000-000000000000'
  for (const [owner, other, url] of probes) {
    expect((await owner.request.get(url)).status(), url).toBe(200)
    const theirs = await other.request.get(url)
    const unknown = await other.request.get(
      url.replace(/[0-9a-f-]{36}/, missing),
    )
    expect(theirs.status(), url).toBeGreaterThanOrEqual(400)
    expect([theirs.status(), await theirs.text()], url).toEqual([
      unknown.status(),
      (await unknown.text()).replaceAll(
        missing,
        url.match(/[0-9a-f-]{36}/)![0],
      ),
    ])
  }
})

test('a correction changes one account’s record and keeps its history', async () => {
  const details = await openAsset(one, first.asset)
  await details.getByText('Make a correction').click()
  const correction = details.getByRole('region', { name: 'Correct this asset' })
  await correction.getByLabel('Change to make').selectOption('ownership')
  await correction.getByLabel('Ownership statement').selectOption('sold')
  await correction
    .getByLabel('Why are you changing it?')
    .fill('Synthetic correction: sold at a yard sale.')
  await correction.getByRole('button', { name: 'Save correction' }).click()
  await expect(details).toContainText('Historical item record')
  await expect(details).toContainText(
    'Synthetic correction: sold at a yard sale.',
  )
  // The earlier stated ownership stays in history next to the correction.
  await expect(details).toContainText('owned: true stated')
  await expect(details).toContainText('owned: false stated')
  await expect(details).toContainText('asset status: "sold" stated')

  // The other account's item with the shared name is untouched.
  const theirs = await openAsset(two, shared)
  await expect(theirs).not.toContainText('Synthetic correction')
  await expect(theirs).not.toContainText('Historical item record')
})

test('sessions, records and the correction survive a server restart', async () => {
  await restartInstallation(sharedPort)
  await one.reload()
  await two.reload()
  await expect(one.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await expect(two.getByRole('button', { name: 'Sign out' })).toBeVisible()

  const details = await openAsset(one, first.asset)
  await expect(details).toContainText(`Manufacturer: ${first.manufacturer}`)
  await expect(details).toContainText('Historical item record')
  await expect(details).toContainText(
    'Synthetic correction: sold at a yard sale.',
  )
  await expect(details).toContainText('owned: true stated')
  await expect(
    details
      .getByRole('region', { name: 'Photos and documents' })
      .getByRole('button', { name: new RegExp(first.photo) }),
  ).toBeVisible()
  await recallStaysSeparate()
})

test('each account’s download holds only its own records', async () => {
  const mine = await readFile(await download(one, false), 'utf8')
  expect(mine).toContain(first.asset)
  expect(mine).toContain('Synthetic correction: sold at a yard sale.')
  for (const word of [
    second.asset,
    second.store,
    second.document,
    secondAccount.email,
  ]) {
    expect(mine).not.toContain(word)
  }

  const theirs = await readFile(await download(two, false), 'utf8')
  expect(theirs).toContain(second.asset)
  expect(theirs).toContain(second.store)
  for (const word of [
    first.asset,
    first.manufacturer,
    first.photo,
    account.email,
  ]) {
    expect(theirs).not.toContain(word)
  }

  firstArchive = await download(one, true)
})

test('restoring another account’s archive is refused; your own changes nothing', async () => {
  expect(firstArchive, 'the download step saves an archive').not.toBe('')
  const refused = await restore(two, firstArchive)
  await expect(refused.getByRole('alert')).toContainText(
    'belong to another account',
  )
  const theirs = await assetNames(two)
  await expect(
    theirs.getByRole('button', { name: first.asset, exact: true }),
  ).toHaveCount(0)
  await expectNothing(two, first.photo)

  const again = await restore(one, firstArchive)
  await expect(again.getByRole('status')).toContainText(
    'Nothing new to restore',
  )
  await expect(again.getByRole('alert')).toHaveCount(0)
  await assetNames(one)
})

test('signing out one account leaves the other signed in', async () => {
  await one.getByRole('button', { name: 'Sign out' }).click()
  await expect(one.getByRole('button', { name: 'Sign in' })).toBeVisible()
  expect((await one.request.get('/api/assets')).status()).toBe(401)
  await two.reload()
  await expect(two.getByRole('button', { name: 'Sign out' })).toBeVisible()
  expect((await two.request.get('/api/assets')).status()).toBe(200)
})
