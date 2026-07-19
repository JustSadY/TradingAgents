import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ErrorBoundary } from '../ErrorBoundary'

const ThrowError = () => {
  throw new Error('Test crash')
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div data-testid="child">OK</div>
      </ErrorBoundary>
    )
    expect(screen.getByTestId('child')).toHaveTextContent('OK')
  })

  it('renders default fallback on error', () => {
    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>
    )
    expect(screen.getByText('Component Crash')).toBeInTheDocument()
    expect(screen.getByText('Reload Page')).toBeInTheDocument()
  })

  it('uses custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<div data-testid="custom">Custom Error</div>}>
        <ThrowError />
      </ErrorBoundary>
    )
    expect(screen.getByTestId('custom')).toHaveTextContent('Custom Error')
  })

  it('shows component name in error message', () => {
    render(
      <ErrorBoundary name="TestWidget">
        <ThrowError />
      </ErrorBoundary>
    )
    expect(screen.getByText(/TestWidget/)).toBeInTheDocument()
  })

  it('resets when children change', () => {
    const { rerender } = render(
      <ErrorBoundary>
        <div>OK</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('OK')).toBeInTheDocument()

    rerender(
      <ErrorBoundary>
        <div>Still OK</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('Still OK')).toBeInTheDocument()
  })
})
