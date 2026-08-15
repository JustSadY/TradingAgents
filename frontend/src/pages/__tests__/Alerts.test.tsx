import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import { QueryClientProvider } from '@tanstack/react-query'
import { appTheme } from '../../theme/appTheme'
import { queryClient } from '../../api/queryClient'
import Alerts from '../Alerts'

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}))

vi.mock('../../contexts/LanguageContext', async () => ({
  useTranslation: (await import('../../test/i18nMock')).useTranslationMock,
}))

vi.mock('../../api/generated/alerts/alerts', () => ({
  getAlertsListAlertsRunQueryKey: () => ['/api/alerts'],
  useAlertsListAlertsRun: () => ({
    data: [{
      id: 7,
      ticker: 'AAPL',
      condition: 'above',
      target_price: 150,
      auto_analyze: true,
      enabled: true,
      triggered_at: null,
      alert_type: 'price',
      creation_source: 'manual',
    }],
    isPending: false,
    error: null,
  }),
  useAlertsCreateAlertRun: () => ({ mutate: mocks.create, isPending: false }),
  useAlertsUpdateAlert: () => ({ mutate: mocks.update, isPending: false }),
  useAlertsDeleteAlert: () => ({ mutate: mocks.remove, isPending: false }),
}))

function renderPage() {
  return render(
    <ThemeProvider theme={appTheme}>
      <QueryClientProvider client={queryClient}>
        <Alerts />
      </QueryClientProvider>
    </ThemeProvider>,
  )
}

beforeEach(() => {
  queryClient.clear()
  mocks.create.mockReset()
  mocks.update.mockReset()
  mocks.remove.mockReset()
})

describe('Alerts', () => {
  it('renders generated API alert data through AppDataGrid', async () => {
    renderPage()
    expect(await screen.findByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('preserves create validation and generated mutation payload', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: 'Add Alert' }))
    expect(screen.getByText('Enter a valid symbol and price.')).toBeInTheDocument()
    expect(mocks.create).not.toHaveBeenCalled()

    await user.type(screen.getByLabelText('Symbol'), 'msft')
    await user.type(screen.getByLabelText('Target Price ($)'), '250')
    await user.click(screen.getByRole('button', { name: 'Add Alert' }))

    expect(mocks.create).toHaveBeenCalledWith(
      {
        data: {
          ticker: 'MSFT',
          condition: 'above',
          target_price: 250,
          auto_analyze: false,
          alert_type: 'price',
        },
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })
})
