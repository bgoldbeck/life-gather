import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import { readFileSync } from 'node:fs'
import { configDefaults, defineConfig } from 'vitest/config'

// https://vite.dev/config/
const sourceVersion = readFileSync(
  new URL('../backend/src/lifegather/version.py', import.meta.url),
  'utf8',
).match(/__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"/)?.[1]
if (!sourceVersion) throw new Error('Application version source is invalid')
const revision = process.env.LIFEGATHER_BUILD_REVISION || null
if (revision && !/^[a-f0-9]{40}$/.test(revision))
  throw new Error('Invalid frontend build revision')

export default defineConfig(({ mode }) => ({
  define: {
    __LIFEGATHER_FRONTEND_BUILD__: JSON.stringify(
      mode === 'test' ? null : { version: sourceVersion, revision },
    ),
  },
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    proxy: {
      '/health': 'http://127.0.0.1:8787',
      '/auth': 'http://127.0.0.1:8787',
      '/api': 'http://127.0.0.1:8787',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    // Browser end-to-end checks run with Playwright: npm run test:e2e.
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
}))
