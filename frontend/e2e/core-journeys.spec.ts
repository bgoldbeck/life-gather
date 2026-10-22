import { readFile } from 'node:fs/promises'
import path from 'node:path'

import { expect, test, type Page } from '@playwright/test'

import { account, openView, primaryURL, secondURL, signIn } from './support.ts'

// The journeys run in order in one signed-in browser session and build on one
// workspace: each later step relies on records saved earlier, like a person
// using the app. All records are synthetic.
test.describe.configure({ mode: 'serial' })

const fixtures = path.join(import.meta.dirname, 'fixtures')
const photoFile = path.join(fixtures, 'synthetic-lamp.png')
const receiptFile = path.join(fixtures, 'synthetic-receipt.txt')
const asset = { name: 'Brass desk lamp', manufacturer: 'Example Lighting' }

let page: Page
let archivePath = ''

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage()
})

test.afterAll(async () => {
  await page.close()
})

async function assetDetails() {
  await openView(page, 'Assets')
  await page
    .getByRole('region', { name: 'Your assets' })
    .getByRole('button', { name: asset.name, exact: true })
    .click()
  const details = page.getByRole('region', { name: 'Asset details' })
  await expect(details.getByRole('heading', { name: asset.name })).toBeVisible()
  return details
}

test('sign in rejects a wrong password, then keeps the session', async () => {
  await page.goto(primaryURL + '/')
  await page.getByRole('textbox', { name: 'Email' }).fill(account.email)
  await page
    .getByRole('textbox', { name: 'Password' })
    .fill('not-the-right-password-at-all')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign out' })).toHaveCount(0)

  await signIn(page)
  await expect(page.getByRole('banner')).toContainText(account.name)

  // The opaque session cookie survives a full reload.
  await page.reload()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
})

test('add an asset; a same-name entry asks before linking', async () => {
  await openView(page, 'Assets')
  const assets = page.getByRole('region', { name: 'Your assets' })
  await assets.getByRole('button', { name: 'Add asset' }).click()
  const form = page.getByRole('region', { name: 'Add asset manually' })
  await form.getByLabel('Asset name').fill(asset.name)
  await form.getByLabel('Manufacturer').fill(asset.manufacturer)
  await form.getByLabel('I currently own this item').check()
  await form.getByRole('button', { name: 'Save asset' }).click()
  await expect(
    assets.getByText(`${asset.name} saved with your stated ownership.`),
  ).toBeVisible()
  const details = page.getByRole('region', { name: 'Asset details' })
  await expect(details).toContainText(`Manufacturer: ${asset.manufacturer}`)

  // Entering the same name again must not silently create or merge a record.
  await assets.getByRole('button', { name: 'Add asset' }).click()
  await form.getByLabel('Asset name').fill(asset.name)
  await form.getByLabel('I currently own this item').check()
  await form.getByRole('button', { name: 'Save asset' }).click()
  await expect(form.getByLabel('Possible duplicate assets')).toBeVisible()
  await expect(
    form.getByRole('button', { name: `Add information to ${asset.name}` }),
  ).toBeVisible()
  await form.getByRole('button', { name: 'Cancel' }).click()
  await expect(
    assets.getByRole('button', { name: asset.name, exact: true }),
  ).toHaveCount(1)
})

test('attach a receipt photo to the asset', async () => {
  const details = await assetDetails()
  const media = details.getByRole('region', { name: 'Photos and documents' })
  await media.getByLabel('Photo file').setInputFiles(photoFile)
  await media.getByLabel('Photo purpose').selectOption('Receipt')
  await media
    .getByRole('button', { name: 'Upload privately to this item' })
    .click()
  await expect(
    media.getByRole('button', { name: /synthetic-lamp\.png/ }),
  ).toBeVisible()

  // The Photos view shows the same photo attached to the asset, and the
  // original downloads byte for byte.
  await openView(page, 'Photos')
  const photos = page.getByRole('region', { name: 'Private photos' })
  await photos.getByRole('button', { name: /synthetic-lamp\.png/ }).click()
  const photo = page.getByRole('region', { name: 'Photo details' })
  await expect(photo.getByText(asset.name)).toBeVisible()
  const download = page.waitForEvent('download')
  await photo.getByRole('link', { name: 'Download original' }).click()
  const saved = await (await download).path()
  expect(await readFile(saved)).toEqual(await readFile(photoFile))
})

test('upload a receipt document and save its reviewed text', async () => {
  await openView(page, 'Documents')
  await page.getByLabel('Document file').setInputFiles(receiptFile)
  await page.getByRole('button', { name: 'Upload document' }).click()
  const review = page.getByRole('region', { name: 'Document review' })
  await expect(review.getByLabel('Reviewed text')).toHaveValue(
    /Example Hardware Store/,
  )
  await review
    .getByRole('button', { name: 'Save reviewed text to memory' })
    .click()
  await expect(
    page.getByRole('button', { name: /synthetic-receipt\.txt/ }),
  ).not.toContainText('Needs text review')
})

test('search everything finds and opens the saved records', async () => {
  const search = page.getByRole('searchbox', {
    name: 'Search assets, photos, documents and sources',
  })
  const results = page.getByRole('region', { name: 'Search results' })

  await search.fill('Brass desk lamp')
  await search.press('Enter')
  await expect(
    results.getByRole('button', { name: new RegExp(asset.name) }).first(),
  ).toBeVisible()
  await results
    .getByRole('region', { name: 'Assets' })
    .getByRole('button', { name: new RegExp(asset.name) })
    .click()
  await expect(
    page
      .getByRole('region', { name: 'Asset details' })
      .getByRole('heading', { name: asset.name }),
  ).toBeVisible()

  await search.fill('Example Hardware Store')
  await search.press('Enter')
  const documents = results.getByRole('region', { name: 'Documents' })
  await documents
    .getByRole('button', { name: /synthetic-receipt\.txt/ })
    .click()
  await expect(
    page
      .getByRole('region', { name: 'Document review' })
      .getByRole('heading', { name: 'synthetic-receipt.txt' }),
  ).toBeVisible()

  await search.fill('zzz unmatched synthetic words')
  await search.press('Enter')
  await expect(results.getByRole('button')).toHaveCount(0)
})

test('back up the workspace as a personal archive with originals', async () => {
  await openView(page, 'Settings')
  const exportCard = page.getByRole('region', { name: 'Download your records' })
  await exportCard
    .getByLabel('Include original photos and documents (ZIP)')
    .check()
  const download = page.waitForEvent('download')
  await exportCard
    .getByRole('button', { name: 'Download archive (ZIP)' })
    .click()
  const archive = await download
  expect(archive.suggestedFilename()).toMatch(/\.zip$/)
  archivePath = test.info().outputPath('personal-archive.zip')
  await archive.saveAs(archivePath)
  await expect(exportCard.getByRole('status').last()).toContainText(
    'download has started',
  )
})

test('restore the archive into a new installation', async ({ browser }) => {
  expect(archivePath, 'the backup journey saves an archive').not.toBe('')
  // A separate browser context, as on another computer.
  const context = await browser.newContext()
  const fresh = await context.newPage()
  await signIn(fresh, secondURL)

  await openView(fresh, 'Assets')
  await expect(
    fresh.getByText('No assets found. Use Add asset', { exact: false }),
  ).toBeVisible()

  await openView(fresh, 'Settings')
  const restore = fresh.getByRole('region', { name: 'Restore your records' })
  await restore.getByLabel('Personal archive (ZIP)').setInputFiles(archivePath)
  await restore.getByLabel("Add this archive's records to my account").check()
  await restore.getByRole('button', { name: 'Restore archive' }).click()
  await expect(restore.getByRole('status')).toContainText(
    /Restored [\d,]+ records and 2 original files/,
  )

  // Restored records are usable: the asset keeps its evidence and photo, the
  // photo original is identical, and the reviewed document is searchable.
  await openView(fresh, 'Assets')
  await fresh
    .getByRole('region', { name: 'Your assets' })
    .getByRole('button', { name: asset.name, exact: true })
    .click()
  const details = fresh.getByRole('region', { name: 'Asset details' })
  await expect(details).toContainText(`Manufacturer: ${asset.manufacturer}`)
  await expect(
    details
      .getByRole('region', { name: 'Photos and documents' })
      .getByRole('button', { name: /synthetic-lamp\.png/ }),
  ).toBeVisible()

  await openView(fresh, 'Photos')
  await fresh.getByRole('button', { name: /synthetic-lamp\.png/ }).click()
  const download = fresh.waitForEvent('download')
  await fresh
    .getByRole('region', { name: 'Photo details' })
    .getByRole('link', { name: 'Download original' })
    .click()
  expect(await readFile(await (await download).path())).toEqual(
    await readFile(photoFile),
  )

  const search = fresh.getByRole('searchbox', {
    name: 'Search assets, photos, documents and sources',
  })
  await search.fill('Example Hardware Store')
  await search.press('Enter')
  await expect(
    fresh
      .getByRole('region', { name: 'Search results' })
      .getByRole('button', { name: /synthetic-receipt\.txt/ }),
  ).toBeVisible()

  // A second restore of the same archive is refused rather than duplicating.
  await openView(fresh, 'Settings')
  await restore.getByLabel('Personal archive (ZIP)').setInputFiles(archivePath)
  await restore.getByLabel("Add this archive's records to my account").check()
  await restore.getByRole('button', { name: 'Restore archive' }).click()
  await expect(restore.getByRole('alert')).toContainText(
    'already has saved records',
  )
  await context.close()
})

test('sign out ends the session', async () => {
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  const response = await page.request.get(primaryURL + '/api/assets')
  expect(response.status()).toBe(401)
})
