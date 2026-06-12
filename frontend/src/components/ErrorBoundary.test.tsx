import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ErrorBoundary } from './ErrorBoundary'

function Bomb(): never {
  throw new Error('boom')
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // React logs the caught error; keep test output clean.
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders children when nothing throws', () => {
    render(
      <ErrorBoundary>
        <div>safe content</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('safe content')).toBeDefined()
  })

  it('shows the default crash UI when a child throws', () => {
    render(
      <ErrorBoundary name="Chart">
        <Bomb />
      </ErrorBoundary>
    )
    expect(screen.getByText('Component Crash')).toBeDefined()
    expect(screen.getByText(/Chart/)).toBeDefined()
  })

  it('prefers a custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div>custom fallback</div>}>
        <Bomb />
      </ErrorBoundary>
    )
    expect(screen.getByText('custom fallback')).toBeDefined()
    expect(screen.queryByText('Component Crash')).toBeNull()
  })
})
