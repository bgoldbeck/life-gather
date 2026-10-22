import { defineConfig, devices } from '@playwright/test'

import { primaryURL } from './e2e/support.ts'

// Browser end-to-end checks against the real backend on PostgreSQL.
// See docs/END_TO_END_CHECKS.md.
// Two independent installations: the journeys run on the first, and the backup
// is restored into the second (a fresh database and data directory).

function installation(port: number) {
  return {
    command: 'uv run --project ../backend --locked python e2e/serve.py',
    url: `http://127.0.0.1:${port}/health`,
    env: { LIFEGATHER_E2E_PORT: String(port) },
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'ignore' as const,
    stderr: 'pipe' as const,
  }
}

export default defineConfig({
  testDir: './e2e',
  // One shared server and account; the journeys build on a single workspace.
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? 'line' : [['list']],
  use: {
    baseURL: primaryURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [installation(8797), installation(8798)],
})
