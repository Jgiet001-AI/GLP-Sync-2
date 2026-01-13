import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from 'lucide-react'

export interface PaginationControlsProps {
  page: number
  totalPages: number
  total: number
  pageSize: number
  itemName?: string
  onPageChange: (page: number) => void
  variant?: 'icon' | 'text'
  theme?: 'violet' | 'sky' | 'purple'
}

/**
 * Generate page numbers for pagination with ellipsis for large ranges
 */
function generatePageNumbers(currentPage: number, totalPages: number): (number | string)[] {
  const pages: (number | string)[] = []
  const delta = 2

  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) {
      pages.push(i)
    }
  } else {
    pages.push(1)

    if (currentPage > delta + 2) {
      pages.push('...')
    }

    const rangeStart = Math.max(2, currentPage - delta)
    const rangeEnd = Math.min(totalPages - 1, currentPage + delta)

    for (let i = rangeStart; i <= rangeEnd; i++) {
      pages.push(i)
    }

    if (currentPage < totalPages - delta - 1) {
      pages.push('...')
    }

    pages.push(totalPages)
  }

  return pages
}

/**
 * PaginationControls - Shared pagination component
 *
 * Supports two variants:
 * - 'icon': Icon-based navigation with First/Previous/Next/Last buttons
 * - 'text': Text-based navigation with Previous/Next buttons
 */
export function PaginationControls({
  page,
  totalPages,
  total,
  pageSize,
  itemName = 'items',
  onPageChange,
  variant = 'icon',
  theme = 'violet',
}: PaginationControlsProps) {
  const startItem = (page - 1) * pageSize + 1
  const endItem = Math.min(page * pageSize, total)

  // Theme color classes
  const themeClasses = {
    violet: 'bg-violet-600 text-white',
    sky: 'bg-sky-500 text-white',
    purple: 'bg-hpe-purple text-white',
  }

  const activeClass = themeClasses[theme]

  if (variant === 'text') {
    // Text variant (ClientsPage style)
    return (
      <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50 bg-slate-900/30">
        <div className="text-sm text-slate-400">
          Showing <span className="font-medium text-white">{startItem.toLocaleString()}</span> to{' '}
          <span className="font-medium text-white">{endItem.toLocaleString()}</span> of{' '}
          <span className="font-medium text-white">{total.toLocaleString()}</span> {itemName}
        </div>

        <div className="flex items-center gap-1">
          {/* Previous button */}
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            className="px-3 py-1.5 text-sm rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>

          {/* Page numbers */}
          <div className="flex items-center gap-1 mx-2">
            {generatePageNumbers(page, totalPages).map((p, idx) =>
              typeof p === 'number' ? (
                <button
                  key={idx}
                  onClick={() => onPageChange(p)}
                  className={`min-w-[36px] px-3 py-1.5 text-sm rounded-lg transition-colors ${
                    p === page
                      ? activeClass
                      : 'border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
                  }`}
                >
                  {p}
                </button>
              ) : (
                <span key={idx} className="px-2 text-slate-500">
                  ...
                </span>
              )
            )}
          </div>

          {/* Next button */}
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page === totalPages}
            className="px-3 py-1.5 text-sm rounded-lg border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  // Icon variant (DevicesList/SubscriptionsList style)
  return (
    <div className="border-t border-slate-700/50 px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">
          Showing {startItem.toLocaleString()} to{' '}
          {endItem.toLocaleString()} of {total.toLocaleString()} {itemName}
        </p>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onPageChange(1)}
            disabled={page === 1}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent"
            aria-label="First page"
          >
            <ChevronsLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page === 1}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent"
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>

          <div className="flex items-center gap-1 px-2">
            {generatePageNumbers(page, totalPages).map((pageNum, idx) =>
              pageNum === '...' ? (
                <span key={`ellipsis-${idx}`} className="px-2 text-slate-500">
                  ...
                </span>
              ) : (
                <button
                  key={pageNum}
                  onClick={() => onPageChange(pageNum as number)}
                  className={`min-w-[2rem] rounded-lg px-3 py-1 text-sm font-medium transition-colors ${
                    page === pageNum
                      ? activeClass
                      : 'text-slate-400 hover:bg-slate-700 hover:text-white'
                  }`}
                >
                  {pageNum}
                </button>
              )
            )}
          </div>

          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page === totalPages}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent"
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            onClick={() => onPageChange(totalPages)}
            disabled={page === totalPages}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent"
            aria-label="Last page"
          >
            <ChevronsRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  )
}
