import axios from 'axios'
import type { components } from './schema'

const api = {
  analysis: {
    run: (body: components['schemas']['AnalysisRunRequest']) =>
      axios.post<components['schemas']['AnalysisRunResponse']>('/api/analysis/run', body),
    getById: (id: number) =>
      axios.get<components['schemas']['AnalysisResultRead']>(`/api/analysis/${id}`),
    list: (params?: { ticker?: string; limit?: number; offset?: number }) =>
      axios.get<components['schemas']['AnalysisListItem'][]>('/api/analysis/history', { params }),
    latest: () =>
      axios.get<components['schemas']['AnalysisResultRead']>('/api/analysis/latest'),
    active: () =>
      axios.get<components['schemas']['ActiveTaskRead'][]>('/api/analysis/active'),
    cancel: (taskId: string) =>
      axios.post<components['schemas']['CancelTaskResponse']>(`/api/analysis/${taskId}/cancel`),
    costEstimate: () =>
      axios.get<components['schemas']['CostEstimateResponse']>('/api/analysis/cost-estimate'),
    abComparison: () =>
      axios.get<components['schemas']['ABComparisonItem'][]>('/api/analysis/ab-comparison'),
    performance: (params?: { ticker?: string }) =>
      axios.get<components['schemas']['backend__schemas__analysis__PerformanceResponse']>('/api/analysis/performance', { params }),
    performanceAttribution: () =>
      axios.get<components['schemas']['PerformanceAttributionResponse']>('/api/analysis/performance-attribution'),
    checkpoints: (id: number) =>
      axios.get<components['schemas']['CheckpointItem'][]>(`/api/analysis/${id}/checkpoints`),
    timeTravel: (id: number, body: { checkpoint_id: string; update_state: Record<string, unknown> }) =>
      axios.post<components['schemas']['TimeTravelResponse']>(`/api/analysis/${id}/time-travel`, body),
    chat: {
      list: (id: number) =>
        axios.get<components['schemas']['ChatMessageRead'][]>(`/api/analysis/${id}/chat`),
      send: (id: number, message: string) =>
        axios.post<components['schemas']['ChatMessageRead']>(`/api/analysis/${id}/chat`, { message }),
    },
    runPortfolio: (body: { tickers: string[]; trade_date?: string; asset_type?: string }) =>
      axios.post<components['schemas']['MultiTickerRunResponse']>('/api/analysis/run-portfolio', body),
    portfolioHistory: (params?: { limit?: number; offset?: number }) =>
      axios.get<components['schemas']['MultiTickerListItem'][]>('/api/analysis/portfolio-history', { params }),
    portfolioById: (id: number) =>
      axios.get<components['schemas']['MultiTickerResultRead']>(`/api/analysis/portfolio/${id}`),
  },
  settings: {
    get: (userId?: number) =>
      axios.get<components['schemas']['SettingsRead']>(userId ? `/api/settings/users/${userId}` : '/api/settings'),
    update: (data: components['schemas']['SettingsUpdate'], userId?: number) =>
      axios.put<components['schemas']['SettingsRead']>(userId ? `/api/settings/users/${userId}` : '/api/settings', data),
    memory: () =>
      axios.get<components['schemas']['MemoryStatusResponse']>('/api/settings/memory'),
    webhookDeliveries: () =>
      axios.get<components['schemas']['WebhookDeliveryRead'][]>('/api/settings/webhook-deliveries'),
    testWebhook: (url: string) =>
      axios.post<components['schemas']['OkResponse']>('/api/settings/test-webhook', { url }),
  },
  trading: {
    portfolio: () =>
      axios.get<components['schemas']['PortfolioResponse']>('/api/trading/portfolio'),
    order: (body: components['schemas']['APIOrderRequest']) =>
      axios.post<components['schemas']['OrderResponse']>('/api/trading/order', body),
    performance: () =>
      axios.get<components['schemas']['PortfolioStatsResponse']>('/api/trading/portfolio-stats'),
    reset: () =>
      axios.post<components['schemas']['ResetResponse']>('/api/trading/reset'),
    riskDashboard: () =>
      axios.get<components['schemas']['RiskDashboardResponse']>('/api/trading/risk-dashboard'),
    rebalance: () =>
      axios.post<components['schemas']['RebalanceResponse']>('/api/trading/rebalance'),
  },
  meta: () =>
    axios.get('/api/meta'),
  share: {
    get: (token: string) =>
      axios.get<components['schemas']['SharedReportResponse']>(`/api/share/${token}`),
  },
} as const

export default api
