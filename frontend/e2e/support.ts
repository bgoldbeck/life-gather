import { expect, type Page } from '@playwright/test'

export const primaryURL = 'http://127.0.0.1:8797'
export const secondURL = 'http://127.0.0.1:8798'

// Matches the synthetic account e2e/serve.py provisions in each installation.
export const account = {
  name: 'E2E Tester',
  email: 'e2e.tester@example.test',
  password: 'synthetic-e2e-password-1',
}

export async function signIn(page: Page, baseURL = primaryURL) {
  await page.goto(baseURL + '/')
  await page.getByRole('textbox', { name: 'Email' }).fill(account.email)
  await page.getByRole('textbox', { name: 'Password' }).fill(account.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
}

export async function openView(page: Page, name: string) {
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('button', { name, exact: true })
    .click()
}
