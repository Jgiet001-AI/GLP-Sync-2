import { X } from 'lucide-react'

/**
 * Filter Chips Component
 * Displays active filters as clickable chips that can be removed
 */

export interface FilterChip {
  key: string
  label: string
  value: string
  displayValue?: string
  color?: 'emerald' | 'sky' | 'violet' | 'amber' | 'rose' | 'slate'
}

interface FilterChipsProps {
  filters: FilterChip[]
  onRemove: (key: string) => void
  onClear?: () => void
  className?: string
}

const colorClasses = {
  emerald: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/20',
  sky: 'bg-sky-500/10 text-sky-400 border-sky-500/30 hover:bg-sky-500/20',
  violet: 'bg-violet-500/10 text-violet-400 border-violet-500/30 hover:bg-violet-500/20',
  amber: 'bg-amber-500/10 text-amber-400 border-amber-500/30 hover:bg-amber-500/20',
  rose: 'bg-rose-500/10 text-rose-400 border-rose-500/30 hover:bg-rose-500/20',
  slate: 'bg-slate-500/10 text-slate-400 border-slate-500/30 hover:bg-slate-500/20',
}

export function FilterChips({ filters, onRemove, onClear, className = '' }: FilterChipsProps) {
  if (filters.length === 0) return null

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
        Active Filters:
      </span>

      {filters.map((filter) => (
        <button
          key={filter.key}
          type="button"
          onClick={() => onRemove(filter.key)}
          className={`group flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-all ${
            colorClasses[filter.color || 'slate']
          }`}
          title={`Remove ${filter.label} filter`}
        >
          <span className="text-slate-400">{filter.label}:</span>
          <span>{filter.displayValue || filter.value}</span>
          <X className="h-3 w-3 opacity-60 group-hover:opacity-100" />
        </button>
      ))}

      {filters.length > 1 && onClear && (
        <button
          type="button"
          onClick={onClear}
          className="flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
        >
          Clear all
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}

/**
 * Hook to convert filter params into FilterChip format
 */
export function useFilterChips(
  params: Record<string, string | undefined>,
  config: Record<string, { label: string; color?: FilterChip['color']; formatValue?: (v: string) => string }>
): FilterChip[] {
  const chips: FilterChip[] = []

  for (const [key, value] of Object.entries(params)) {
    if (value && config[key]) {
      const { label, color, formatValue } = config[key]
      chips.push({
        key,
        label,
        value,
        displayValue: formatValue ? formatValue(value) : value,
        color,
      })
    }
  }

  return chips
}

/**
 * Compact filter chip for inline display
 */
export function CompactFilterChip({
  label,
  value,
  onRemove,
  color = 'slate',
}: {
  label: string
  value: string
  onRemove: () => void
  color?: FilterChip['color']
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${colorClasses[color]}`}
    >
      <span className="text-slate-400">{label}:</span>
      <span>{value}</span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onRemove()
        }}
        className="ml-0.5 rounded p-0.5 hover:bg-white/10"
        aria-label={`Remove ${label} filter`}
      >
        <X className="h-2.5 w-2.5" />
      </button>
    </span>
  )
}
