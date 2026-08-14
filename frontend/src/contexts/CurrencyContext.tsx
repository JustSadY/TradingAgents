import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { useMarketGetFxRates } from '../api/generated/market/market'

const STORAGE_KEY = 'ta_currency'

export const CURRENCIES = ['USD', 'EUR', 'GBP', 'TRY', 'JPY', 'CAD', 'AUD', 'CHF'] as const
export type Currency = typeof CURRENCIES[number]

const SYMBOLS: Record<Currency, string> = {
  USD: '$', EUR: '€', GBP: '£', TRY: '₺', JPY: '¥', CAD: 'CA$', AUD: 'A$', CHF: 'Fr',
}

interface CurrencyCtx {
  currency: Currency
  setCurrency: (c: Currency) => void
  symbol: string
  /** Convert a USD amount to the selected currency */
  convert: (usd: number) => number
  /** Format a USD amount as a string in the selected currency */
  fmt: (usd: number, decimals?: number) => string
  rates: Record<string, number | null>
  loadingRates: boolean
}

const Ctx = createContext<CurrencyCtx>({
  currency: 'USD',
  setCurrency: () => {},
  symbol: '$',
  convert: x => x,
  fmt: (x, d = 2) => `$${x.toFixed(d)}`,
  rates: {},
  loadingRates: false,
})

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [currency, _setCurrency] = useState<Currency>(
    () => (localStorage.getItem(STORAGE_KEY) as Currency) || 'USD'
  )
  const ratesQuery = useMarketGetFxRates()
  // Fall back to USD-only so a failed FX fetch renders unconverted USD rather
  // than multiplying by an undefined rate.
  const rates = (ratesQuery.data ?? { USD: 1 }) as Record<string, number | null>
  const loadingRates = ratesQuery.isFetching
  const fetchRates = useCallback(() => { ratesQuery.refetch() }, [ratesQuery])

  const setCurrency = useCallback((c: Currency) => {
    localStorage.setItem(STORAGE_KEY, c)
    _setCurrency(c)
    fetchRates()
  }, [fetchRates])

  const rate = rates[currency] ?? 1

  const convert = useCallback((usd: number) => usd * rate, [rate])

  const fmt = useCallback((usd: number, decimals = 2) => {
    const val = usd * rate
    const sym = SYMBOLS[currency]
    // JPY and TRY have no cents by convention
    const dec = currency === 'JPY' ? 0 : decimals
    return `${sym}${val.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec })}`
  }, [currency, rate])

  return (
    <Ctx.Provider value={{ currency, setCurrency, symbol: SYMBOLS[currency], convert, fmt, rates, loadingRates }}>
      {children}
    </Ctx.Provider>
  )
}

export function useCurrency() { return useContext(Ctx) }
