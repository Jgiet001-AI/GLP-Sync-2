import { useMemo, memo, useState, useTransition } from 'react'
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from '@tanstack/react-table'
import { Check, X, Minus, ChevronUp, ChevronDown } from 'lucide-react'
import clsx from 'clsx'
import type { DeviceAssignment } from '../types'

interface DeviceTableProps {
  devices: DeviceAssignment[]
  selectedSerials: Set<string>
  onToggle: (serial: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
}

const columnHelper = createColumnHelper<DeviceAssignment>()

const StatusBadge = memo(function StatusBadge({ status }: { status: DeviceAssignment['status'] }) {
  const config = {
    not_in_db: { label: 'Not Found', className: 'badge-error' },
    fully_assigned: { label: 'Complete', className: 'badge-success' },
    partial: { label: 'Partial', className: 'badge-warning' },
    unassigned: { label: 'Unassigned', className: 'badge-info' },
  }

  const { label, className } = config[status]

  return <span className={clsx('badge', className)}>{label}</span>
})

const AssignmentCell = memo(function AssignmentCell({ value, label }: { value: boolean | null; label: string }) {
  if (value === true) {
    return <Check className="w-5 h-5 text-emerald-400" aria-label={`${label}: Yes`} />
  }
  if (value === false) {
    return <X className="w-5 h-5 text-rose-400" aria-label={`${label}: No`} />
  }
  return <Minus className="w-5 h-5 text-slate-500" aria-label={`${label}: N/A`} />
})

export function DeviceTable({
  devices,
  selectedSerials,
  onToggle,
  onSelectAll,
  onDeselectAll,
}: DeviceTableProps) {
  const [sorting, setSorting] = useState<SortingState>([])
  const [isPending, startTransition] = useTransition()

  // Wrap sorting updates in transition for non-blocking UI
  const handleSortingChange = (updater: SortingState | ((old: SortingState) => SortingState)) => {
    startTransition(() => {
      setSorting(updater)
    })
  }

  const allSelected = selectedSerials.size === devices.length && devices.length > 0
  const someSelected = selectedSerials.size > 0 && selectedSerials.size < devices.length

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: 'select',
        header: () => (
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => {
              if (el) el.indeterminate = someSelected
            }}
            onChange={(e) =>
              e.target.checked ? onSelectAll() : onDeselectAll()
            }
            aria-label={allSelected ? 'Deselect all devices' : 'Select all devices'}
            data-testid="select-all-checkbox"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={selectedSerials.has(row.original.serial_number)}
            onChange={() => onToggle(row.original.serial_number)}
            aria-label={`Select device ${row.original.serial_number}`}
            data-testid={`select-device-${row.original.serial_number}`}
          />
        ),
      }),
      columnHelper.accessor('serial_number', {
        header: 'Serial Number',
        cell: (info) => (
          <span className="font-mono text-sm text-slate-200">{info.getValue()}</span>
        ),
      }),
      columnHelper.accessor('mac_address', {
        header: 'MAC Address',
        cell: (info) => (
          <span className="font-mono text-sm text-slate-400">
            {info.getValue() || '-'}
          </span>
        ),
      }),
      columnHelper.accessor('device_type', {
        header: 'Type',
        cell: (info) => <span className="text-slate-300">{info.getValue() || '-'}</span>,
      }),
      columnHelper.accessor('model', {
        header: 'Model',
        cell: (info) => <span className="text-slate-300">{info.getValue() || '-'}</span>,
      }),
      columnHelper.accessor('status', {
        header: 'Status',
        cell: (info) => <StatusBadge status={info.getValue()} />,
      }),
      columnHelper.accessor('current_subscription_key', {
        header: 'Subscription',
        cell: (info) =>
          info.getValue() ? (
            <span className="font-mono text-xs text-slate-300">{info.getValue()}</span>
          ) : (
            <span className="text-slate-500">None</span>
          ),
      }),
      columnHelper.accessor('region', {
        header: 'Region',
        cell: (info) => info.getValue() ? (
          <span className="text-slate-300">{info.getValue()}</span>
        ) : (
          <span className="text-slate-500">None</span>
        ),
      }),
      columnHelper.display({
        id: 'hasSubscription',
        header: 'Sub',
        cell: ({ row }) => (
          <AssignmentCell value={row.original.current_subscription_id !== null} label="Has subscription" />
        ),
      }),
      columnHelper.display({
        id: 'hasApplication',
        header: 'App',
        cell: ({ row }) => (
          <AssignmentCell value={row.original.current_application_id !== null} label="Has application" />
        ),
      }),
      columnHelper.display({
        id: 'hasTags',
        header: 'Tags',
        cell: ({ row }) => (
          <AssignmentCell
            value={Object.keys(row.original.current_tags).length > 0}
            label="Has tags"
          />
        ),
      }),
    ],
    [allSelected, someSelected, onDeselectAll, onSelectAll, onToggle, selectedSerials]
  )

  const table = useReactTable({
    data: devices,
    columns,
    state: { sorting },
    onSortingChange: handleSortingChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  return (
    <div
      className={clsx('overflow-x-auto relative', isPending && 'opacity-70 transition-opacity')}
      data-testid="device-table-container"
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
      <table className="w-full" data-testid="device-table">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-slate-700">
              {headerGroup.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-4 py-3 text-left text-sm font-medium text-slate-400 bg-slate-800/50"
                  onClick={header.column.getCanSort() ? header.column.getToggleSortingHandler() : undefined}
                  onKeyDown={(e) => {
                    if (header.column.getCanSort() && (e.key === 'Enter' || e.key === ' ')) {
                      e.preventDefault()
                      header.column.toggleSorting()
                    }
                  }}
                  tabIndex={header.column.getCanSort() ? 0 : undefined}
                  role={header.column.getCanSort() ? 'button' : undefined}
                  aria-sort={
                    header.column.getIsSorted() === 'asc'
                      ? 'ascending'
                      : header.column.getIsSorted() === 'desc'
                        ? 'descending'
                        : undefined
                  }
                  style={{ cursor: header.column.getCanSort() ? 'pointer' : 'default' }}
                >
                  <div className="flex items-center gap-1">
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext()
                    )}
                    {header.column.getIsSorted() === 'asc' && (
                      <ChevronUp className="w-4 h-4 text-hpe-green" aria-hidden="true" />
                    )}
                    {header.column.getIsSorted() === 'desc' && (
                      <ChevronDown className="w-4 h-4 text-hpe-green" aria-hidden="true" />
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
              className={clsx(
                'border-b border-slate-700/50 hover:bg-slate-800/50 transition-colors',
                selectedSerials.has(row.original.serial_number) && 'bg-hpe-green/5'
              )}
              data-testid={`device-row-${row.original.serial_number}`}
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

      {devices.length === 0 && (
        <div className="p-8 text-center text-slate-500" data-testid="device-table-empty">
          No devices to display
        </div>
      )}
    </div>
  )
}
