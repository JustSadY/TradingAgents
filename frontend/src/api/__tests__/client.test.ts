import { describe, it, expect, vi, beforeEach } from 'vitest'
import api from '../client'

vi.mock('axios', async () => {
  const actual = await vi.importActual('axios')
  const mockAxios = {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    defaults: {},
  }
  return { default: mockAxios, ...mockAxios }
})

let axios: any
beforeEach(async () => {
  axios = await import('axios')
  vi.clearAllMocks()
})

describe('api.analysis', () => {
  it('run posts to /api/analysis/run', async () => {
    await api.analysis.run({ ticker: 'AAPL', trade_date: '2026-07-20' })
    expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/run', { ticker: 'AAPL', trade_date: '2026-07-20' })
  })

  it('getById gets /api/analysis/{id}', async () => {
    await api.analysis.getById(42)
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/42')
  })

  it('list gets /api/analysis/history with params', async () => {
    await api.analysis.list({ ticker: 'AAPL', limit: 10 })
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/history', { params: { ticker: 'AAPL', limit: 10 } })
  })

  it('list gets /api/analysis/history without params', async () => {
    await api.analysis.list()
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/history', { params: undefined })
  })

  it('latest gets /api/analysis/latest', async () => {
    await api.analysis.latest()
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/latest')
  })

  it('active gets /api/analysis/active', async () => {
    await api.analysis.active()
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/active')
  })

  it('cancel posts to /api/analysis/{taskId}/cancel', async () => {
    await api.analysis.cancel('abc-123')
    expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/abc-123/cancel')
  })

  it('costEstimate gets /api/analysis/cost-estimate', async () => {
    await api.analysis.costEstimate()
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/cost-estimate')
  })

  it('abComparison gets /api/analysis/ab-comparison', async () => {
    await api.analysis.abComparison()
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/ab-comparison')
  })

  it('performance gets /api/analysis/performance with params', async () => {
    await api.analysis.performance({ ticker: 'AAPL' })
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/performance', { params: { ticker: 'AAPL' } })
  })

  it('performanceAttribution gets /api/analysis/performance-attribution', async () => {
    await api.analysis.performanceAttribution()
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/performance-attribution')
  })

  it('checkpoints gets /api/analysis/{id}/checkpoints', async () => {
    await api.analysis.checkpoints(7)
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/7/checkpoints')
  })

  it('timeTravel posts to /api/analysis/{id}/time-travel', async () => {
    await api.analysis.timeTravel(1, { checkpoint_id: 'cp1', update_state: {} })
    expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/1/time-travel', { checkpoint_id: 'cp1', update_state: {} })
  })

  it('chat.list gets /api/analysis/{id}/chat', async () => {
    await api.analysis.chat.list(5)
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/5/chat')
  })

  it('chat.send posts to /api/analysis/{id}/chat', async () => {
    await api.analysis.chat.send(5, 'Hello')
    expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/5/chat', { message: 'Hello' })
  })

  it('runPortfolio posts to /api/analysis/run-portfolio', async () => {
    await api.analysis.runPortfolio({ tickers: ['AAPL', 'GOOGL'] })
    expect(axios.default.post).toHaveBeenCalledWith('/api/analysis/run-portfolio', { tickers: ['AAPL', 'GOOGL'] })
  })

  it('portfolioHistory gets /api/analysis/portfolio-history with params', async () => {
    await api.analysis.portfolioHistory({ limit: 5 })
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/portfolio-history', { params: { limit: 5 } })
  })

  it('portfolioById gets /api/analysis/portfolio/{id}', async () => {
    await api.analysis.portfolioById(3)
    expect(axios.default.get).toHaveBeenCalledWith('/api/analysis/portfolio/3')
  })
})

describe('api.settings', () => {
  it('get fetches own settings without userId', async () => {
    await api.settings.get()
    expect(axios.default.get).toHaveBeenCalledWith('/api/settings')
  })

  it('get fetches user settings with userId', async () => {
    await api.settings.get(99)
    expect(axios.default.get).toHaveBeenCalledWith('/api/settings/users/99')
  })

  it('update puts own settings without userId', async () => {
    await api.settings.update({ language: 'tr' })
    expect(axios.default.put).toHaveBeenCalledWith('/api/settings', { language: 'tr' })
  })

  it('update puts user settings with userId', async () => {
    await api.settings.update({ language: 'en' }, 99)
    expect(axios.default.put).toHaveBeenCalledWith('/api/settings/users/99', { language: 'en' })
  })

  it('memory gets /api/settings/memory', async () => {
    await api.settings.memory()
    expect(axios.default.get).toHaveBeenCalledWith('/api/settings/memory')
  })

  it('webhookDeliveries gets /api/settings/webhook-deliveries', async () => {
    await api.settings.webhookDeliveries()
    expect(axios.default.get).toHaveBeenCalledWith('/api/settings/webhook-deliveries')
  })

  it('testWebhook posts to /api/settings/test-webhook', async () => {
    await api.settings.testWebhook('https://hooks.example.com')
    expect(axios.default.post).toHaveBeenCalledWith('/api/settings/test-webhook', { url: 'https://hooks.example.com' })
  })
})

describe('api.trading', () => {
  it('portfolio gets /api/trading/portfolio', async () => {
    await api.trading.portfolio()
    expect(axios.default.get).toHaveBeenCalledWith('/api/trading/portfolio')
  })

  it('order posts to /api/trading/order', async () => {
    await api.trading.order({ ticker: 'AAPL', action: 'buy', quantity: 10 })
    expect(axios.default.post).toHaveBeenCalledWith('/api/trading/order', { ticker: 'AAPL', action: 'buy', quantity: 10 })
  })

  it('performance gets /api/trading/portfolio-stats', async () => {
    await api.trading.performance()
    expect(axios.default.get).toHaveBeenCalledWith('/api/trading/portfolio-stats')
  })

  it('reset posts to /api/trading/reset', async () => {
    await api.trading.reset()
    expect(axios.default.post).toHaveBeenCalledWith('/api/trading/reset')
  })

  it('riskDashboard gets /api/trading/risk-dashboard', async () => {
    await api.trading.riskDashboard()
    expect(axios.default.get).toHaveBeenCalledWith('/api/trading/risk-dashboard')
  })

  it('rebalance posts to /api/trading/rebalance', async () => {
    await api.trading.rebalance()
    expect(axios.default.post).toHaveBeenCalledWith('/api/trading/rebalance')
  })
})

describe('api.meta', () => {
  it('fetches /api/meta', async () => {
    await api.meta()
    expect(axios.default.get).toHaveBeenCalledWith('/api/meta')
  })

  it('returns meta data from response', async () => {
    const mockData = { analysts: [{ key: 'market', label: 'Market Analyst' }] }
    axios.default.get.mockResolvedValue({ data: mockData })
    const result = await api.meta()
    expect(result.data).toEqual(mockData)
  })
})

describe('api.share', () => {
  it('get fetches /api/share/{token}', async () => {
    await api.share.get('abc123')
    expect(axios.default.get).toHaveBeenCalledWith('/api/share/abc123')
  })
})

describe('api module structure', () => {
  it('exports nested namespaces', () => {
    expect(api.analysis).toBeDefined()
    expect(api.settings).toBeDefined()
    expect(api.trading).toBeDefined()
    expect(api.meta).toBeDefined()
    expect(api.share).toBeDefined()
  })
})
