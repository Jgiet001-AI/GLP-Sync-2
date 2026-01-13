import { useCallback } from 'react'
import { useUrlState } from './useUrlState'

/**
 * Configuration for paginated list state
 */
export interface PaginatedListConfig<TFilters extends Record<string, string | undefined>> {
  /** Initial page number (default: 1) */
  page?: number
  /** Initial page size (default: 100) */
  page_size?: number
  /** Initial sort field (default: 'updated_at') */
  sort_by?: string
  /** Initial sort direction (default: 'desc') */
  sort_order?: 'asc' | 'desc'
  /** Additional filter fields */
  filters?: TFilters
}

/**
 * State returned by usePaginatedList
 */
export interface PaginatedListState<TFilters extends Record<string, string | undefined>> {
  page: number
  page_size: number
  sort_by: string
  sort_order: 'asc' | 'desc'
  filters: TFilters
}

/**
 * Handlers returned by usePaginatedList
 */
export interface PaginatedListHandlers<TFilters extends Record<string, string | undefined>> {
  /** Change the current page */
  handlePageChange: (newPage: number) => void
  /** Change the page size and reset to page 1 */
  handlePageSizeChange: (newSize: number) => void
  /** Toggle sort order for a column */
  handleSort: (column: string) => void
  /** Update a single filter value and reset to page 1 */
  handleFilterChange: (key: keyof TFilters, value: string | undefined) => void
  /** Update multiple filters at once and reset to page 1 */
  handleFiltersChange: (updates: Partial<TFilters>) => void
  /** Clear all filters and sorting, reset to defaults */
  clearFilters: () => void
}

/**
 * Hook for common paginated list page state management
 * Combines pagination, sorting, and filtering with URL synchronization
 *
 * Addresses common pattern from DevicesList, SubscriptionsList, and ClientsPage:
 * - Bidirectional URL param sync for all state
 * - Pagination with page and page_size
 * - Column sorting with sort_by and sort_order
 * - Extensible filter fields
 *
 * @example
 * ```tsx
 * // Define your filter fields
 * interface DeviceFilters {
 *   device_type?: string
 *   region?: string
 *   assigned_state?: string
 *   search?: string
 * }
 *
 * // Use the hook
 * const { state, handlers } = usePaginatedList<DeviceFilters>({
 *   page: 1,
 *   page_size: 100,
 *   sort_by: 'updated_at',
 *   sort_order: 'desc',
 *   filters: {
 *     device_type: undefined,
 *     region: undefined,
 *     assigned_state: undefined,
 *     search: undefined,
 *   }
 * })
 *
 * // Use in query
 * const { data } = useQuery({
 *   queryKey: ['devices', state],
 *   queryFn: () => api.getDevices(state)
 * })
 *
 * // Use handlers
 * <button onClick={() => handlers.handlePageChange(2)}>Page 2</button>
 * <button onClick={() => handlers.handleSort('name')}>Sort by Name</button>
 * <input onChange={(e) => handlers.handleFilterChange('search', e.target.value)} />
 * ```
 */
export function usePaginatedList<TFilters extends Record<string, string | undefined>>(
  config: PaginatedListConfig<TFilters>
): {
  state: PaginatedListState<TFilters>
  handlers: PaginatedListHandlers<TFilters>
} {
  const {
    page = 1,
    page_size = 100,
    sort_by = 'updated_at',
    sort_order = 'desc',
    filters = {} as TFilters,
  } = config

  // Define combined state type for URL synchronization
  type CombinedState = {
    page: number
    page_size: number
    sort_by: string
    sort_order: 'asc' | 'desc'
  } & TFilters

  // Combine all state into a single URL-synced object
  const defaultState: CombinedState = {
    page,
    page_size,
    sort_by,
    sort_order,
    ...filters,
  } as CombinedState

  const [urlState, setUrlState, clearUrlState] = useUrlState(defaultState)

  // Extract structured state from URL state
  const state: PaginatedListState<TFilters> = {
    page: Number(urlState.page) || page,
    page_size: Number(urlState.page_size) || page_size,
    sort_by: (urlState.sort_by as string) || sort_by,
    sort_order: (urlState.sort_order as 'asc' | 'desc') || sort_order,
    filters: Object.keys(filters).reduce((acc, key) => {
      const value = urlState[key] as string | undefined
      acc[key as keyof TFilters] = value as TFilters[keyof TFilters]
      return acc
    }, {} as TFilters),
  }

  // Pagination handlers
  const handlePageChange = useCallback(
    (newPage: number) => {
      setUrlState({ page: newPage } as Partial<CombinedState>)
    },
    [setUrlState]
  )

  const handlePageSizeChange = useCallback(
    (newSize: number) => {
      setUrlState({ page_size: newSize, page: 1 } as Partial<CombinedState>)
    },
    [setUrlState]
  )

  // Sorting handler
  const handleSort = useCallback(
    (column: string) => {
      const newSortOrder =
        state.sort_by === column && state.sort_order === 'asc' ? 'desc' : 'asc'
      setUrlState({
        sort_by: column,
        sort_order: newSortOrder,
      } as Partial<CombinedState>)
    },
    [state.sort_by, state.sort_order, setUrlState]
  )

  // Filter handlers
  const handleFilterChange = useCallback(
    (key: keyof TFilters, value: string | undefined) => {
      setUrlState({
        [key as string]: value || undefined,
        page: 1, // Reset to page 1 when filters change
      } as Partial<CombinedState>)
    },
    [setUrlState]
  )

  const handleFiltersChange = useCallback(
    (updates: Partial<TFilters>) => {
      setUrlState({
        ...updates,
        page: 1, // Reset to page 1 when filters change
      } as Partial<CombinedState>)
    },
    [setUrlState]
  )

  // Clear all filters and reset to defaults
  const clearFilters = useCallback(() => {
    clearUrlState()
  }, [clearUrlState])

  return {
    state,
    handlers: {
      handlePageChange,
      handlePageSizeChange,
      handleSort,
      handleFilterChange,
      handleFiltersChange,
      clearFilters,
    },
  }
}
