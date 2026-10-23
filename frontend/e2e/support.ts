import { existsSync } from 'node:fs'
import { writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'

import { expect, type Page } from '@playwright/test'

export const primaryURL = 'http://127.0.0.1:8797'
export const secondURL = 'http://127.0.0.1:8798'
// Two accounts share this installation; see two-account-loop.spec.ts.
export const sharedURL = 'http://127.0.0.1:8799'
export const sharedPort = 8799

// Matches the synthetic account e2e/serve.py provisions in each installation.
export const account = {
  name: 'E2E Tester',
  email: 'e2e.tester@example.test',
  password: 'synthetic-e2e-password-1',
}

// The second account e2e/serve.py provisions with LIFEGATHER_E2E_TWO_ACCOUNTS.
export const secondAccount = {
  name: 'E2E Second Tester',
  email: 'e2e.second@example.test',
  password: 'synthetic-e2e-password-2',
}

export async function signIn(
  page: Page,
  baseURL = primaryURL,
  who: typeof account = account,
) {
  await page.goto(baseURL + '/')
  await page.getByRole('textbox', { name: 'Email' }).fill(who.email)
  await page.getByRole('textbox', { name: 'Password' }).fill(who.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

export async function openView(page: Page, name: string) {
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('button', { name, exact: true })
    .click()
}

// Asks e2e/serve.py to stop the server process and start a new one on the same
// database and data directory, then waits until the new process answers.
export async function restartInstallation(port: number) {
  const marker = path.join(tmpdir(), `lifegather-e2e-${port}.restart`)
  await writeFile(marker, '')
  await expect.poll(() => existsSync(marker), { timeout: 60_000 }).toBe(false)
  await expect
    .poll(
      async () => {
        try {
          return (await fetch(`http://127.0.0.1:${port}/health`)).status
        } catch {
          return 0
        }
      },
      { timeout: 60_000 },
    )
    .toBe(200)
}
