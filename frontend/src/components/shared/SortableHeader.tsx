import { memo } from 'react'
import { ArrowUpDown } from 'lucide-react'

interface SortableHeaderProps {
  column: string
  label: string
  currentSort?: string
  sortOrder?: string
  onSort: (column: string) => void
}

export const SortableHeader = memo(function SortableHeader({
  column,
  label,
  currentSort,
  sortOrder,
  onSort,
}: SortableHeaderProps) {
  const isActive = currentSort === column

  return (
    <th
      className="cursor-pointer px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-400 transition-colors hover:text-white"
      onClick={() => onSort(column)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSort(column)
        }
      }}
      tabIndex={0}
      role="button"
      aria-sort={isActive ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
    >
      <div className="flex items-center gap-1">
        {label}
        <ArrowUpDown
          className={`h-3.5 w-3.5 ${isActive ? 'text-hpe-green' : 'text-slate-600'}`}
          aria-hidden="true"
        />
        {isActive && (
          <span className="text-hpe-green" aria-hidden="true">{sortOrder === 'asc' ? '↑' : '↓'}</span>
        )}
      </div>
    </th>
  )
})
