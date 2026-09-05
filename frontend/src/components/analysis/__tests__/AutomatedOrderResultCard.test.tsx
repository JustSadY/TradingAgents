import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AutomatedOrderResultCard } from '../AutomatedOrderResultCard'

vi.mock('../../../contexts/LanguageContext', async () => ({
  useTranslation: (await import('../../../test/i18nMock')).useTranslationMock,
}))

describe('AutomatedOrderResultCard', () => {
  it('shows the broker order id for reconciliation', () => {
    render(
      <AutomatedOrderResultCard
        result={{
          outcome: 'reconciliation_required',
          action: 'BUY',
          ticker: 'NVDA',
          orderId: 'alpaca-reconcile-42',
          message: 'Reconcile the Alpaca account before retrying.',
        }}
      />,
    )

    expect(screen.getByText('Broker reconciliation required')).toBeInTheDocument()
    expect(screen.getByText('Broker Order ID')).toBeInTheDocument()
    expect(screen.getByText('alpaca-reconcile-42')).toBeInTheDocument()
    expect(screen.getByTestId('analysis-order-result')).toHaveAttribute('data-outcome', 'reconciliation_required')
  })
})
