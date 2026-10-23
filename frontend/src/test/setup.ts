import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { XHRViaFetch } from './xhrViaFetch'

globalThis.XMLHttpRequest = XHRViaFetch as unknown as typeof XMLHttpRequest
afterEach(cleanup)
