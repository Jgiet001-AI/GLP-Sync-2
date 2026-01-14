import { useMemo, useState, useTransition } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
  type ColumnDef,
} from '@tanstack/react-table'
import { ChevronUp, ChevronDown, Download, FileSpreadsheet, AlertCircle, Clock } from 'lucide-react'
import clsx from 'clsx'
import type { ExecuteReportResponse } from '../../types'

interface ReportPreviewProps {
  data: ExecuteReportResponse | null
  isLoading: boolean
  onDownload: (format: 'csv' | 'xlsx') => void
}

export function ReportPreview({ data, isLoading, onDownload }: ReportPreviewProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [isPending, startTransition] = useTransition()

  // Wrap sorting updates in transition for non-blocking UI
  const handleSortingChange = (updater: SortingState | ((old: SortingState) => SortingState)) => {
    startTransition(() => {
      setSorting(updater)
    })
  }

  // Generate dynamic columns from data
  const columns = useMemo<ColumnDef<Record<string, any>>[]>(() => {
    if (!data || !data.columns.length) {
      return []
    }

    const columnHelper = createColumnHelper<Record<string, any>>()

    return data.columns.map((columnName) =>
      columnHelper.accessor(columnName, {
        header: columnName,
        cell: (info) => {
          const value = info.getValue()

          // Handle null/undefined
          if (value === null || value === undefined) {
            return <span className="text-slate-500 italic">null</span>
          }

          // Handle boolean
          if (typeof value === 'boolean') {
            return <span className="text-slate-300">{value ? 'true' : 'false'}</span>
          }

          // Handle numbers
          if (typeof value === 'number') {
            return <span className="font-mono text-sm text-slate-300">{value.toLocaleString()}</span>
          }

          // Handle objects/arrays
          if (typeof value === 'object') {
            return <span className="font-mono text-xs text-slate-400">{JSON.stringify(value)}</span>
          }

          // Default string rendering
          return <span className="text-slate-300">{String(value)}</span>
        },
      })
    )
  }, [data?.columns])

  const table = useReactTable({
    data: data?.data || [],
    columns,
    state: { sorting },
    onSortingChange: handleSortingChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  // Loading state
  if (isLoading) {
    return (
      <div className="card" data-testid="report-preview-loading">
        <div className="card-body">
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <div
                className="h-12 w-12 mx-auto mb-4 animate-spin rounded-full border-4 border-slate-600 border-t-hpe-green"
                role="status"
                aria-label="Loading report preview"
              />
              <p className="text-slate-400">Executing report...</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Empty state
  if (!data) {
    return (
      <div className="card" data-testid="report-preview-empty">
        <div className="card-body">
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <FileSpreadsheet className="w-12 h-12 mx-auto mb-4 text-slate-600" />
              <p className="text-slate-400">
                Configure your report and click <strong>Run Report</strong> to see results
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Error state
  if (!data.success || data.errors.length > 0) {
    return (
      <div className="card" data-testid="report-preview-error">
        <div className="card-body">
          <div className="flex items-center justify-center py-12">
            <div className="text-center max-w-md">
              <AlertCircle className="w-12 h-12 mx-auto mb-4 text-rose-500" />
              <p className="text-slate-300 mb-2 font-medium">Report execution failed</p>
              {data.errors.map((error, idx) => (
                <p key={idx} className="text-sm text-rose-400 mb-1">
                  {error}
                </p>
              ))}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // No results
  if (data.total_rows === 0) {
    return (
      <div className="card" data-testid="report-preview-no-results">
        <div className="card-body">
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <FileSpreadsheet className="w-12 h-12 mx-auto mb-4 text-slate-600" />
              <p className="text-slate-400">No results found for this report configuration</p>
              <p className="text-sm text-slate-500 mt-2">Try adjusting your filters or criteria</p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="card" data-testid="report-preview">
      <div className="card-body">
        {/* Header with metadata and export buttons */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-4 text-sm">
            <span className="text-slate-400">
              <strong className="text-slate-200">{data.total_rows.toLocaleString()}</strong> rows
            </span>
            <span className="text-slate-500">•</span>
            <span className="text-slate-400 flex items-center gap-1">
              <Clock className="w-4 h-4" />
              {data.execution_time_ms}ms
            </span>
            {data.page > 1 || data.total_rows > data.page_size ? (
              <>
                <span className="text-slate-500">•</span>
                <span className="text-slate-400">
                  Page {data.page} (showing {data.data.length} of {data.total_rows})
                </span>
              </>
            ) : null}
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => onDownload('csv')}
              className="btn btn-sm btn-secondary flex items-center gap-2"
              data-testid="export-csv-button"
            >
              <Download className="w-4 h-4" />
              CSV
            </button>
            <button
              onClick={() => onDownload('xlsx')}
              className="btn btn-sm btn-secondary flex items-center gap-2"
              data-testid="export-excel-button"
            >
              <FileSpreadsheet className="w-4 h-4" />
              Excel
            </button>
          </div>
        </div>

        {/* Results table */}
        <div
          className={clsx(
            'overflow-x-auto relative border border-slate-700 rounded-lg',
            isPending && 'opacity-70 transition-opacity'
          )}
          data-testid="report-preview-table-container"
        >
          {isPending && (
            <div className="absolute inset-0 flex items-center justify-center bg-slate-900/50 z-10">
              <div
                className="h-6 w-6 animate-spin rounded-full border-2 border-slate-600 border-t-hpe-green"
                role="status"
                aria-label="Sorting table"
              />
            </div>
          )}
          <table className="w-full" data-testid="report-preview-table">
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} className="border-b border-slate-700">
                  {headerGroup.headers.map((header) => (
                    <th
                      key={header.id}
                      className={clsx(
                        'px-4 py-3 text-left text-sm font-medium text-slate-400 bg-slate-800/50',
                        header.column.getCanSort() && 'cursor-pointer select-none hover:bg-slate-800'
                      )}
                      onClick={header.column.getToggleSortingHandler()}
                      onKeyDown={(e) => {
                        if (header.column.getCanSort() && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault()
                          header.column.getToggleSortingHandler()?.(e as any)
                        }
                      }}
                      tabIndex={header.column.getCanSort() ? 0 : undefined}
                      role={header.column.getCanSort() ? 'button' : undefined}
                      aria-sort={
                        header.column.getIsSorted()
                          ? header.column.getIsSorted() === 'asc'
                            ? 'ascending'
                            : 'descending'
                          : undefined
                      }
                    >
                      <div className="flex items-center gap-2">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() && (
                          <span className="text-slate-500">
                            {header.column.getIsSorted() === 'asc' ? (
                              <ChevronUp className="w-4 h-4" />
                            ) : header.column.getIsSorted() === 'desc' ? (
                              <ChevronDown className="w-4 h-4" />
                            ) : (
                              <div className="w-4 h-4" />
                            )}
                          </span>
                        )}
                      </div>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors"
                  data-testid={`report-preview-row-${row.id}`}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 text-sm">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Show SQL query in development */}
        {data.generated_sql && (
          <details className="mt-4">
            <summary className="text-sm text-slate-500 cursor-pointer hover:text-slate-400">
              Show generated SQL
            </summary>
            <pre className="mt-2 p-3 bg-slate-900 border border-slate-700 rounded text-xs text-slate-400 overflow-x-auto font-mono">
              {data.generated_sql}
            </pre>
          </details>
        )}
      </div>
    </div>
  )
}
