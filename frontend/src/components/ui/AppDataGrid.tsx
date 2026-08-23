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
        sx={{ minHeight, display: 'grid', placeItems: 'center' }}
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
          border: 'none',
          backgroundColor: 'transparent',
          borderRadius: 0,
          // The grid ships its own 14px cell text; matching the theme's control
          // size keeps a table the same weight as the Tailwind tables beside it.
          fontSize: 12,
          '& .MuiDataGrid-columnHeaders': {
            backgroundColor: 'rgba(255,255,255,.02)',
            color: 'text.secondary',
            textTransform: 'uppercase',
            fontSize: 10,
            letterSpacing: '.08em',
          },
          // The grid centres single-line text by setting `line-height` on the
          // cell to the row height. Anything rendered by `renderCell` inherits
          // it, so a 10px badge became a 63px box that spilled past the row
          // rules and a two-line cell was clipped by `overflow: hidden`.
          // Centring with flexbox instead, and resetting the inherited
          // line-height, fixes both for every table at once — and does not
          // break again when a row height changes.
          '& .MuiDataGrid-cell': {
            borderColor: 'rgba(255,255,255,.04)',
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            lineHeight: 'normal',
          },
          '& .MuiTablePagination-root': { fontSize: 11 },
          '& .MuiDataGrid-row:hover': { backgroundColor: 'rgba(255,255,255,.025)' },
          '& .MuiDataGrid-footerContainer': { borderColor: 'rgba(255,255,255,.04)' },
          ...sx,
        }}
        {...props}
      />
    </Box>
  )
}


export function formatMoney(value: number | null | undefined, currency = 'USD', locale?: string): string {
  if (value == null || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat(locale, { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
}



export default AppDataGrid
