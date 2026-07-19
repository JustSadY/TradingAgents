import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CurrencyProvider, useCurrency, CURRENCIES } from '../CurrencyContext'
import type { ReactNode } from 'react'

const mockFxRates = vi.hoisted((): Record<string, number | null> => ({
  USD: 1, EUR: 0.92, GBP: 0.79, TRY: 30.5, JPY: 149.5,
  CAD: 1.36, AUD: 1.53, CHF: 0.88,
}))

vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  return {
    ...actual,
    default: {
      ...(actual as any).default,
      get: vi.fn().mockResolvedValue({ data: mockFxRates }),
      post: vi.fn().mockResolvedValue({ data: {} }),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
      defaults: {},
    },
  }
})

function TestConsumer() {
  const { currency, setCurrency, symbol, convert, fmt, rates, loadingRates } = useCurrency()
  return (
    <div>
      <span data-testid="currency">{currency}</span>
      <span data-testid="symbol">{symbol}</span>
      <span data-testid="convert">{convert(100)}</span>
      <span data-testid="fmt">{fmt(100)}</span>
      <span data-testid="fmt-jpy">{fmt(100, 2)}</span>
      <span data-testid="loading">{String(loadingRates)}</span>
      <select data-testid="select" value={currency} onChange={e => setCurrency(e.target.value as any)}>
        {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    </div>
  )
}

function renderWithCurrency(children: ReactNode) {
  return render(<CurrencyProvider>{children}</CurrencyProvider>)
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

afterEach(() => {
  localStorage.clear()
})

describe('CurrencyContext', () => {
  it('defaults to USD', () => {
    renderWithCurrency(<TestConsumer />)
    expect(screen.getByTestId('currency')).toHaveTextContent('USD')
    expect(screen.getByTestId('symbol')).toHaveTextContent('$')
  })

  it('fetches FX rates on mount', async () => {
    renderWithCurrency(<TestConsumer />)
    await waitFor(() => {
      expect(screen.getByTestId('loading')).toHaveTextContent('false')
    })
  })

  it('convert returns same value for USD', async () => {
    renderWithCurrency(<TestConsumer />)
    await waitFor(() => {
      expect(screen.getByTestId('convert')).toHaveTextContent('100')
    })
  })

  it('convert applies rate for non-USD', async () => {
    renderWithCurrency(<TestConsumer />)
    await waitFor(() => {
      const select = screen.getByTestId('select')
    })
    await userEvent.selectOptions(screen.getByTestId('select'), 'TRY')
    await waitFor(() => {
      expect(screen.getByTestId('convert')).toHaveTextContent('3050')
    })
  })

  it('fmt formats USD value', async () => {
    renderWithCurrency(<TestConsumer />)
    await waitFor(() => {
      expect(screen.getByTestId('fmt')).toHaveTextContent('$100.00')
    })
  })

  it('fmt formats JPY with 0 decimals', async () => {
    renderWithCurrency(<TestConsumer />)
    await waitFor(() => {
      const select = screen.getByTestId('select')
    })
    await userEvent.selectOptions(screen.getByTestId('select'), 'JPY')
    await waitFor(() => {
      expect(screen.getByTestId('fmt')).toHaveTextContent('¥14,950')
      expect(screen.getByTestId('fmt-jpy')).toHaveTextContent('¥14,950')
    })
  })

  it('persists currency to localStorage', async () => {
    renderWithCurrency(<TestConsumer />)
    await userEvent.selectOptions(screen.getByTestId('select'), 'EUR')
    expect(localStorage.getItem('ta_currency')).toBe('EUR')
  })
})
