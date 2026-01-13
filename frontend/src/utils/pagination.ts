export const PAGE_SIZE_OPTIONS = [10, 100, 500, 1000]

export function generatePageNumbers(currentPage: number, totalPages: number): (number | string)[] {
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
