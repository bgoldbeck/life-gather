import path from 'node:path'

import { devices, expect, test } from '@playwright/test'

import { openView, secondURL, signIn } from './support.ts'

// Phone camera capture: on a touch screen, "Take a photo" opens the rear camera
// through the ordinary file input (Playwright hands it a file instead), saves the
// photo straight away with progress and Cancel, and attaches it in Chat.
// Runs on the second installation after core-journeys has restored into it.

const cameraPhoto = path.join(
  import.meta.dirname,
  'fixtures',
  'synthetic-camera-receipt.jpg',
)

test('takes a photo into Photos and Chat on a phone', async ({ browser }) => {
  const { defaultBrowserType: _, ...phone } = devices['Pixel 7']
  const context = await browser.newContext({ ...phone, baseURL: secondURL })
  const page = await context.newPage()
  await signIn(page, secondURL)

  // Hold the first upload so Cancel is visible, then cancel it.
  let held = true
  await page.route('**/api/photos?purpose=*', async (route) => {
    if (route.request().method() !== 'POST' || !held) return route.fallback()
    held = false
    await new Promise((resolve) => setTimeout(resolve, 3_000))
    await route.abort()
  })

  await openView(page, 'Photos')
  const photos = page.getByRole('region', { name: 'Private photos' })
  await photos.getByLabel('Photo purpose').selectOption('Receipt')
  const camera = photos.getByLabel('Take a photo', { exact: true })
  await expect(camera).toHaveAttribute('capture', 'environment')
  await expect(
    photos.locator('label.camera-capture', { hasText: 'Take a photo' }),
  ).toBeVisible()
  await camera.setInputFiles(cameraPhoto)
  await expect(
    photos.getByRole('progressbar', { name: 'Photo upload progress' }),
  ).toBeVisible()
  await photos.getByRole('button', { name: 'Cancel upload' }).click()
  await expect(photos.getByText(/Upload cancelled/)).toBeVisible()

  // Sending the same photo again saves it once.
  await photos.getByRole('button', { name: 'Upload privately' }).click()
  await expect(
    photos.getByText('Photo saved privately. No AI request was made.'),
  ).toBeVisible()
  await expect(
    photos.getByRole('button', { name: /synthetic-camera-receipt\.jpg/ }),
  ).toHaveCount(1)

  // Chat: review a receipt photo taken with the camera. The same photo is
  // already saved, so it is selected without a second copy.
  await page.getByRole('button', { name: 'Expand assistant' }).click()
  const chat = page.getByRole('region', { name: 'Your personal assistant' })
  await chat.getByLabel('Action').selectOption('Review a receipt photo')
  await chat
    .getByLabel('Take a photo for Chat', { exact: true })
    .setInputFiles(cameraPhoto)
  await expect(chat.getByText('Selected photo:')).toContainText(
    'synthetic-camera-receipt.jpg',
  )
  await expect(
    chat.getByRole('button', {
      name: 'Choose photo synthetic-camera-receipt.jpg',
    }),
  ).toHaveCount(1)

  await context.close()
})

test('hides the camera button on a desktop browser', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: secondURL })
  const page = await context.newPage()
  await signIn(page, secondURL)
  await openView(page, 'Photos')
  const photos = page.getByRole('region', { name: 'Private photos' })
  await expect(photos.getByLabel('Photo file')).toBeVisible()
  await expect(
    photos.locator('label.camera-capture', { hasText: 'Take a photo' }),
  ).toBeHidden()
  await context.close()
})
