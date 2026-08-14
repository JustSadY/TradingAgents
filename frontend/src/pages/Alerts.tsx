import { useState } from 'react'
import { Chip, IconButton, Stack } from '@mui/material'
import type { GridColDef } from '@mui/x-data-grid'
import { useQueryClient } from '@tanstack/react-query'
import { Bell, BellOff, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { useTranslation } from '../contexts/LanguageContext'
import {
  useAlertsListAlertsRun,
  useAlertsCreateAlertRun,
  useAlertsUpdateAlert,
  useAlertsDeleteAlert,
  getAlertsListAlertsRunQueryKey,
} from '../api/generated/alerts/alerts'
import type { AlertRead } from '../api/generated/model'
import { AppDataGrid, formatMoney } from '../components/ui/AppDataGrid'
import {
  AppAlert,
  AppButton,
  AppSelect,
  AppSwitch,
  AppTextField,
  AppTooltip,
} from '../components/ui/AppPrimitives'

export default function Alerts() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [ticker, setTicker] = useState('')
  const [condition, setCondition] = useState<'above' | 'below'>('above')
  const [targetPrice, setTargetPrice] = useState('')
  const [alertType, setAlertType] = useState<'price' | 'rsi' | 'macd_cross'>('price')
  const [autoAnalyze, setAutoAnalyze] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const alertsQuery = useAlertsListAlertsRun()
  const alerts = alertsQuery.data ?? []

  const invalidate = () => queryClient.invalidateQueries({ queryKey: getAlertsListAlertsRunQueryKey() })
  const createMutation = useAlertsCreateAlertRun({ mutation: { onSuccess: invalidate } })
  const updateMutation = useAlertsUpdateAlert({ mutation: { onSuccess: invalidate } })
  const deleteMutation = useAlertsDeleteAlert({ mutation: { onSuccess: invalidate } })

  const handleCreate = () => {
    const symbol = ticker.trim().toUpperCase()
    const needsPrice = alertType !== 'macd_cross'
    const price = needsPrice ? Number.parseFloat(targetPrice) : 0
    if (!symbol || (needsPrice && (Number.isNaN(price) || price <= 0))) {
      setError(t('alerts.error_invalid'))
      return
    }

    setError(null)
    createMutation.mutate(
      { data: { ticker: symbol, condition, target_price: price, auto_analyze: autoAnalyze, alert_type: alertType } },
      {
        onSuccess: () => {
          setTicker('')
          setTargetPrice('')
          setAutoAnalyze(false)
        },
        onError: err => {
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
          setError(detail || t('alerts.error_create'))
        },
      },
    )
  }

  const columns: GridColDef<AlertRead>[] = [
    {
      field: 'ticker',
      headerName: t('alerts.col_symbol'),
      minWidth: 150,
      flex: 1,
      renderCell: params => (
        <Stack direction="row" alignItems="center" spacing={0.75} sx={{ height: '100%' }}>
          <strong className="font-mono text-white">{params.row.ticker}</strong>
          {params.row.alert_type && params.row.alert_type !== 'price' ? (
            <Chip size="small" label={params.row.alert_type} variant="outlined" color="info" sx={{ height: 20, fontSize: 9 }} />
          ) : null}
          {params.row.creation_source === 'analysis' ? (
            <Chip size="small" label={t('alerts.source_ai')} variant="outlined" color="secondary" sx={{ height: 20, fontSize: 9 }} />
          ) : null}
        </Stack>
      ),
    },
    {
      field: 'condition',
      headerName: t('alerts.col_condition'),
      minWidth: 130,
      flex: 0.8,
      renderCell: params => params.row.condition === 'above'
        ? `↑ ${t('alerts.condition_above')}`
        : `↓ ${t('alerts.condition_below')}`,
    },
    {
      field: 'target_price',
      headerName: t('alerts.col_target'),
      minWidth: 120,
      align: 'right',
      headerAlign: 'right',
      renderCell: params => params.row.alert_type === 'rsi'
        ? Number(params.row.target_price).toLocaleString()
        : formatMoney(Number(params.row.target_price)),
    },
    {
      field: 'auto_analyze',
      headerName: t('alerts.col_auto'),
      minWidth: 90,
      align: 'center',
      headerAlign: 'center',
      renderCell: params => params.row.auto_analyze ? '✓' : '—',
    },
    {
      field: 'enabled',
      headerName: t('alerts.col_status'),
      minWidth: 120,
      align: 'center',
      headerAlign: 'center',
      renderCell: params => {
        if (params.row.triggered_at) return <Chip size="small" color="warning" variant="outlined" label={t('alerts.status_triggered')} />
        if (params.row.enabled) return <Chip size="small" color="success" variant="outlined" label={t('alerts.status_active')} />
        return <Chip size="small" variant="outlined" label={t('alerts.status_inactive')} />
      },
    },
    {
      field: 'actions',
      headerName: t('alerts.col_action'),
      sortable: false,
      filterable: false,
      minWidth: 110,
      align: 'center',
      headerAlign: 'center',
      renderCell: params => (
        <Stack direction="row" spacing={0.25} alignItems="center" sx={{ height: '100%' }}>
          <AppTooltip title={params.row.enabled ? t('alerts.btn_deactivate') : t('alerts.btn_activate')}>
            <span>
              <IconButton
                size="small"
                disabled={updateMutation.isPending}
                aria-label={params.row.enabled ? t('alerts.btn_deactivate') : t('alerts.btn_activate')}
                onClick={() => updateMutation.mutate({ alertId: params.row.id, data: { enabled: !params.row.enabled } })}
              >
                {params.row.enabled ? <Bell size={15} /> : <BellOff size={15} />}
              </IconButton>
            </span>
          </AppTooltip>
          <AppTooltip title={t('alerts.col_action')}>
            <span>
              <IconButton
                size="small"
                color="error"
                disabled={deleteMutation.isPending}
                aria-label={`Delete ${params.row.ticker}`}
                onClick={() => deleteMutation.mutate({ alertId: params.row.id })}
              >
                <Trash2 size={15} />
              </IconButton>
            </span>
          </AppTooltip>
        </Stack>
      ),
    },
  ]

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl md:text-2xl font-display font-bold text-white tracking-tight">{t('alerts.title')}</h2>
        <p className="text-xs text-slate-500 mt-1">Set price threshold targets to dispatch webhook triggers or auto-run graphs</p>
      </div>

      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <h3 className="text-xs font-bold text-violet-400 uppercase tracking-widest">{t('alerts.new_alert')}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <AppTextField
            label={t('alerts.symbol')}
            placeholder="AAPL"
            value={ticker}
            onChange={event => setTicker(event.target.value.toUpperCase())}
          />
          <AppSelect
            id="alert-type"
            label={t('alerts.type')}
            value={alertType}
            options={[
              { value: 'price', label: t('alerts.type_price') },
              { value: 'rsi', label: t('alerts.type_rsi') },
              { value: 'macd_cross', label: t('alerts.type_macd_cross') },
            ]}
            onChange={value => setAlertType(value as typeof alertType)}
          />
          <AppSelect
            id="alert-condition"
            label={t('alerts.condition')}
            value={condition}
            options={[
              { value: 'above', label: alertType === 'macd_cross' ? t('alerts.condition_bullish') : t('alerts.condition_above') },
              { value: 'below', label: alertType === 'macd_cross' ? t('alerts.condition_bearish') : t('alerts.condition_below') },
            ]}
            onChange={value => setCondition(value as typeof condition)}
          />
          {alertType !== 'macd_cross' ? (
            <AppTextField
              type="number"
              label={alertType === 'rsi' ? t('alerts.rsi_threshold') : t('alerts.target_price')}
              value={targetPrice}
              placeholder={alertType === 'rsi' ? '70' : '150.00'}
              slotProps={{ htmlInput: { step: '0.01' } }}
              onChange={event => setTargetPrice(event.target.value)}
            />
          ) : null}
          <AppSwitch checked={autoAnalyze} label={t('alerts.auto_analyze')} onChange={setAutoAnalyze} />
        </div>

        {error ? <AppAlert severity="error">{error}</AppAlert> : null}
        <AppButton onClick={handleCreate} disabled={createMutation.isPending} startIcon={createMutation.isPending ? <RefreshCw size={14} className="animate-spin" /> : <Plus size={14} />}>
          {t('alerts.add_button')}
        </AppButton>
      </div>

      <div className="glass-panel rounded-2xl p-4 space-y-3">
        <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest">
          {t('alerts.active_alerts')} ({alerts.filter(alert => alert.enabled && !alert.triggered_at).length})
        </h3>
        <AppDataGrid
          rows={alerts}
          columns={columns}
          loading={alertsQuery.isPending}
          error={alertsQuery.error}
          emptyMessage={t('alerts.empty')}
          ariaLabel={t('alerts.active_alerts')}
          getRowClassName={params => params.row.triggered_at ? 'opacity-50' : ''}
        />
      </div>
    </div>
  )
}
