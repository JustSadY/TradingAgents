import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi, beforeEach } from 'vitest'

class MockResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

window.ResizeObserver = MockResizeObserver as any

Element.prototype.scrollTo = vi.fn() as any
Element.prototype.scrollIntoView = vi.fn() as any

const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
    get length() { return Object.keys(store).length },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
})()

beforeEach(() => {
  localStorageMock.clear()
})

afterEach(() => {
  cleanup()
})

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
  configurable: true,
})

const sessionStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { store = {} },
    get length() { return Object.keys(store).length },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
})()

beforeEach(() => {
  sessionStorageMock.clear()
})

Object.defineProperty(window, 'sessionStorage', {
  value: sessionStorageMock,
  writable: true,
  configurable: true,
})

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock)

// Use Object.defineProperty for read-only globalThis.crypto
Object.defineProperty(globalThis, 'crypto', {
  value: {
    ...globalThis.crypto,
    randomUUID: () => '00000000-0000-0000-0000-000000000000',
  },
  writable: true,
  configurable: true,
})

vi.mock('axios', () => {
  // The Orval-generated client calls the *callable* form, `axios(config)`,
  // through src/api/mutator.ts, while hand-written call sites still use
  // axios.get/post/... Support both: the callable dispatches to the same method
  // mocks, so a test that stubs `axios.get` also controls generated queries.
  const methods = {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  }

  const mockAxios = Object.assign(
    vi.fn((config: { url?: string; method?: string; data?: unknown } = {}) => {
      const method = String(config.method ?? 'get').toLowerCase() as keyof typeof methods
      // Read the handler off the object, not the closure, so a test that does
      // `vi.spyOn(axios, 'get')` also intercepts generated-client requests.
      const handler = (mockAxios[method] ?? mockAxios.get) as (...args: never[]) => unknown
      return handler(config.url as never, config as never)
    }),
    methods,
    {
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
      defaults: {},
    },
  )

  return { default: mockAxios, ...methods, interceptors: mockAxios.interceptors, defaults: mockAxios.defaults }
})

