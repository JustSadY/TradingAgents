import type { GridColDef } from '@mui/x-data-grid'
import { ArrowRight } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { SignalBadge } from '../analysis/SignalBadge'
import AppDataGrid from '../ui/AppDataGrid'
import { AppButton } from '../ui/AppPrimitives'

interface RecentAnalysisRow {
  id: number | string
  ticker: string
  trade_date?: string | null
  signal?: string | null
  duration_seconds?: number | null
}

interface RecentAnalysisTableProps {
  recentAnalysis: RecentAnalysisRow[]
  t: (key: string) => string
}

export function RecentAnalysisTable({ recentAnalysis, t }: RecentAnalysisTableProps) {
  const navigate = useNavigate()

  const columns: GridColDef<RecentAnalysisRow>[] = [
    {
      field: 'ticker',
      headerName: 'Ticker',
      minWidth: 150,
      flex: 1,
      renderCell: params => (
        <div className="flex flex-col justify-center h-full">
          <span className="font-mono font-bold text-white">{params.row.ticker}</span>
          <span className="text-[10px] text-slate-500">{params.row.trade_date ?? '—'}</span>
        </div>
      ),
    },
    {
      field: 'signal',
      headerName: 'Signal',
      minWidth: 120,
      align: 'center',
      headerAlign: 'center',
      renderCell: params => <SignalBadge signal={params.row.signal ?? null} />,
    },
    {
      field: 'duration_seconds',
      headerName: 'Duration',
      minWidth: 110,
      align: 'right',
      headerAlign: 'right',
      renderCell: params => <span className="text-slate-500 font-mono text-[10px]">{(params.row.duration_seconds ?? 0).toFixed(1)}s</span>,
    },
  ]

  return (
    <div className="lg:col-span-2 glass-panel rounded-2xl overflow-hidden flex flex-col">
      <div className="px-5 py-4 border-b border-white/[0.04] bg-slate-900/20 flex items-center justify-between">
        <h3 className="text-xs font-bold text-white uppercase tracking-widest">{t('dashboard.recent_analysis')}</h3>
        <AppButton
          variant="text"
          endIcon={<ArrowRight size={11} />}
          onClick={() => navigate('/analysis')}
          sx={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '.08em' }}
        >
          {t('dashboard.view_all')}
        </AppButton>
      </div>
      <div className="flex-1 p-2">
        <AppDataGrid
          rows={recentAnalysis}
          columns={columns}
          emptyMessage="No recent analysis found"
          ariaLabel={t('dashboard.recent_analysis')}
          hideFooter
          minHeight={220}
          onRowClick={params => navigate(`/analysis?id=${params.row.id}`)}
          sx={{ '& .MuiDataGrid-row': { cursor: 'pointer' } }}
        />
      </div>
    </div>
  )
}

export default RecentAnalysisTable
