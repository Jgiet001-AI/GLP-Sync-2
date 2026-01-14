/**
 * Pagination utilities
 *
 * Extracted from DevicesList, SubscriptionsList, and ClientsPage to reduce duplication.
 * Provides consistent pagination behavior across all list pages.
 */

/**
 * Standard page size options available across the application
 *
 * Users can select from these options to control how many items
 * are displayed per page in list views.
 */
export const PAGE_SIZE_OPTIONS = [10, 100, 500, 1000]

/**
 * Generate page numbers for pagination controls with smart ellipsis
 *
 * Creates an array of page numbers with ellipsis ("...") for long ranges.
 * Ensures the first page, last page, and pages near the current page are always visible.
 *
 * Algorithm:
 * - For 7 or fewer pages: show all pages
 * - For more pages: show first, last, and 2 pages on each side of current page
 * - Use "..." to indicate gaps in the sequence
 *
 * @param currentPage - The currently active page (1-indexed)
 * @param totalPages - Total number of pages available
 * @returns Array of page numbers and ellipsis strings
 *
 * @example
 * ```tsx
 * // With 5 total pages
 * generatePageNumbers(3, 5) // [1, 2, 3, 4, 5]
 *
 * // With 20 total pages, on page 10
 * generatePageNumbers(10, 20) // [1, "...", 8, 9, 10, 11, 12, "...", 20]
 *
 * // With 20 total pages, on page 2
 * generatePageNumbers(2, 20) // [1, 2, 3, 4, "...", 20]
 *
 * // With 20 total pages, on page 19
 * generatePageNumbers(19, 20) // [1, "...", 17, 18, 19, 20]
 * ```
 */
export function generatePageNumbers(currentPage: number, totalPages: number): (number | string)[] {
  const pages: (number | string)[] = []
  const delta = 2 // Number of pages to show on each side of current page

  // For small page counts, show all pages
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) {
      pages.push(i)
    }
  } else {
    // Always show first page
    pages.push(1)

    // Add leading ellipsis if current page is far from start
    if (currentPage > delta + 2) {
      pages.push('...')
    }

    // Calculate range around current page
    const rangeStart = Math.max(2, currentPage - delta)
    const rangeEnd = Math.min(totalPages - 1, currentPage + delta)

    // Add pages in the range around current page
    for (let i = rangeStart; i <= rangeEnd; i++) {
      pages.push(i)
    }

    // Add trailing ellipsis if current page is far from end
    if (currentPage < totalPages - delta - 1) {
      pages.push('...')
    }

    // Always show last page
    pages.push(totalPages)
  }

  return pages
}
