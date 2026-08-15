import { Box, Typography } from '@mui/material'
import {
  DataGrid,
  type DataGridProps,
  type GridColDef,
  type GridValidRowModel,
} from '@mui/x-data-grid'
import { AppAlert, AppSkeleton } from './AppPrimitives'

export type AppDataGridProps<R extends GridValidRowModel = GridValidRowModel> = Omit<
  DataGridProps<R>,
  'rows' | 'columns'
> & {
  rows: readonly R[]
  columns: readonly GridColDef<R>[]
  error?: unknown
  emptyMessage?: string
  ariaLabel?: string
  minHeight?: number
}

function getErrorMessage(error: unknown): string {
  if (!error) return ''
  if (error instanceof Error) return error.message
  if (typeof error === 'object') {
    const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return 'Unable to load data.'
}

export function AppDataGrid<R extends GridValidRowModel>({
  rows,
  columns,
  error,
  emptyMessage = 'No data found.',
  ariaLabel = 'Data table',
  minHeight = 240,
  loading = false,
  pageSizeOptions = [10, 25, 50],
  initialState,
  sx,
  ...props
}: AppDataGridProps<R>) {
  if (error) {
    return <AppAlert severity="error">{getErrorMessage(error)}</AppAlert>
  }

  if (loading && rows.length === 0) {
    return (
      <Box aria-label={`${ariaLabel} loading`} sx={{ display: 'grid', gap: 1, py: 1 }}>
        <AppSkeleton variant="rounded" height={44} />
        <AppSkeleton variant="rounded" height={44} />
        <AppSkeleton variant="rounded" height={44} />
      </Box>
    )
  }

  if (!loading && rows.length === 0) {
    return (
      <Box
        role="status"
        sx={{ minHeight, display: 'grid', placeItems: 'center', border: '1px solid', borderColor: 'divider', borderRadius: 2, backgroundColor: 'rgba(15,23,42,.35)' }}
      >
        <Typography variant="body2" color="text.secondary">{emptyMessage}</Typography>
      </Box>
    )
  }

  return (
    <Box sx={{ width: '100%', minHeight, overflowX: 'auto' }}>
      <DataGrid<R>
        rows={rows}
        columns={columns}
        loading={loading}
        pageSizeOptions={pageSizeOptions}
        disableRowSelectionOnClick
        aria-label={ariaLabel}
        initialState={initialState ?? { pagination: { paginationModel: { page: 0, pageSize: 10 } } }}
        sx={{
          minWidth: 620,
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          backgroundColor: 'rgba(15, 23, 42, 0.38)',
          backdropFilter: 'blur(16px)',
          '& .MuiDataGrid-columnHeaders': {
            backgroundColor: 'rgba(255,255,255,.02)',
            color: 'text.secondary',
            textTransform: 'uppercase',
            fontSize: 10,
            letterSpacing: '.08em',
          },
          '& .MuiDataGrid-cell': { borderColor: 'rgba(255,255,255,.04)' },
          '& .MuiDataGrid-row:hover': { backgroundColor: 'rgba(255,255,255,.025)' },
          '& .MuiDataGrid-footerContainer': { borderColor: 'rgba(255,255,255,.04)' },
          ...sx,
        }}
        {...props}
      />
    </Box>
  )
}

export function formatDate(value: string | number | Date | null | undefined, locale?: string): string {
  if (value == null || value === '') return '—'
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function formatMoney(value: number | null | undefined, currency = 'USD', locale?: string): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(locale, { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
}

export function formatCount(value: number | null | undefined, locale?: string): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(value)
}

export function formatPercent(value: number | null | undefined, locale?: string): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 2 }).format(value)
}

export default AppDataGrid
