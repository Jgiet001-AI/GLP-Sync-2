import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Client filter types matching the API schema
 */
export type ClientType = 'Wired' | 'Wireless'
export type ClientStatus = 'Connected' | 'Disconnected' | 'Failed' | 'Blocked'
export type ClientHealth = 'Good' | 'Fair' | 'Poor' | 'Unknown'

export interface ClientsFilters {
  type?: ClientType[]
  status?: ClientStatus[]
  health?: ClientHealth[]
  site_id?: string[]
  network?: string[]
  vlan?: string[]
  role?: string[]
  tunnel?: string[]
  auth?: string[]
  key_mgmt?: string[]
  connected_to?: string[]
  subnet?: string
  search?: string
}

// All array filter keys
type ArrayFilterKey = 'type' | 'status' | 'health' | 'site_id' | 'network' | 'vlan' | 'role' | 'tunnel' | 'auth' | 'key_mgmt' | 'connected_to'

/**
 * Filter presets for quick KPI card clicks
 */
export type FilterPreset =
  | 'all'
  | 'connected'
  | 'disconnected'
  | 'wireless'
  | 'wired'
  | 'health_good'
  | 'health_fair'
  | 'health_poor'

// Helper to parse comma-delimited arrays from URL
function parseArrayParam<T extends string>(value: string | null): T[] | undefined {
  if (!value) return undefined
  const items = value.split(',').filter(Boolean) as T[]
  return items.length > 0 ? items : undefined
}

// Helper to serialize arrays to comma-delimited URL params
function serializeArrayParam(values: string[] | undefined): string | null {
  if (!values || values.length === 0) return null
  return values.join(',')
}

/**
 * Hook for managing client filters via URL state
 *
 * Features:
 * - Syncs filter state with URL search params
 * - Supports multi-select arrays (comma-delimited)
 * - Resets pagination when filters change
 * - Provides preset filters for KPI card clicks
 */
export function useClientsFilters() {
  const [searchParams, setSearchParams] = useSearchParams()

  // Parse filters from URL
  const filters = useMemo<ClientsFilters>(() => ({
    type: parseArrayParam<ClientType>(searchParams.get('type')),
    status: parseArrayParam<ClientStatus>(searchParams.get('status')),
    health: parseArrayParam<ClientHealth>(searchParams.get('health')),
    site_id: parseArrayParam<string>(searchParams.get('site_id')),
    network: parseArrayParam<string>(searchParams.get('network')),
    vlan: parseArrayParam<string>(searchParams.get('vlan')),
    role: parseArrayParam<string>(searchParams.get('role')),
    tunnel: parseArrayParam<string>(searchParams.get('tunnel')),
    auth: parseArrayParam<string>(searchParams.get('auth')),
    key_mgmt: parseArrayParam<string>(searchParams.get('key_mgmt')),
    connected_to: parseArrayParam<string>(searchParams.get('connected_to')),
    subnet: searchParams.get('subnet') || undefined,
    search: searchParams.get('search') || undefined,
  }), [searchParams])

  // Check if any filters are active
  const hasFilters = useMemo(() => {
    return Boolean(
      filters.type?.length ||
      filters.status?.length ||
      filters.health?.length ||
      filters.site_id?.length ||
      filters.network?.length ||
      filters.vlan?.length ||
      filters.role?.length ||
      filters.tunnel?.length ||
      filters.auth?.length ||
      filters.key_mgmt?.length ||
      filters.connected_to?.length ||
      filters.subnet ||
      filters.search
    )
  }, [filters])

  // Count active filters
  const activeFilterCount = useMemo(() => {
    let count = 0
    if (filters.type?.length) count++
    if (filters.status?.length) count++
    if (filters.health?.length) count++
    if (filters.site_id?.length) count++
    if (filters.network?.length) count++
    if (filters.vlan?.length) count++
    if (filters.role?.length) count++
    if (filters.tunnel?.length) count++
    if (filters.auth?.length) count++
    if (filters.key_mgmt?.length) count++
    if (filters.connected_to?.length) count++
    if (filters.subnet) count++
    if (filters.search) count++
    return count
  }, [filters])

  // Get filter summary for display
  const filterSummary = useMemo(() => {
    const parts: string[] = []
    if (filters.type?.length) parts.push(`Type: ${filters.type.join(', ')}`)
    if (filters.status?.length) parts.push(`Status: ${filters.status.join(', ')}`)
    if (filters.health?.length) parts.push(`Health: ${filters.health.join(', ')}`)
    if (filters.site_id?.length) parts.push(`Sites: ${filters.site_id.length}`)
    if (filters.network?.length) parts.push(`Networks: ${filters.network.length}`)
    if (filters.vlan?.length) parts.push(`VLANs: ${filters.vlan.length}`)
    if (filters.role?.length) parts.push(`Roles: ${filters.role.length}`)
    if (filters.tunnel?.length) parts.push(`Tunnels: ${filters.tunnel.join(', ')}`)
    if (filters.auth?.length) parts.push(`Auth: ${filters.auth.length}`)
    if (filters.key_mgmt?.length) parts.push(`Key Mgmt: ${filters.key_mgmt.length}`)
    if (filters.connected_to?.length) parts.push(`Devices: ${filters.connected_to.length}`)
    if (filters.subnet) parts.push(`Subnet: ${filters.subnet}`)
    if (filters.search) parts.push(`Search: "${filters.search}"`)
    return parts.join(' | ')
  }, [filters])

  // Set a single filter value (replace mode)
  const setFilter = useCallback(<K extends keyof ClientsFilters>(
    key: K,
    value: ClientsFilters[K]
  ) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams(prev)

      // Always reset pagination when filters change
      newParams.delete('page')

      if (value === undefined || value === null || (Array.isArray(value) && value.length === 0)) {
        newParams.delete(key)
      } else if (Array.isArray(value)) {
        const serialized = serializeArrayParam(value as string[])
        if (serialized) {
          newParams.set(key, serialized)
        } else {
          newParams.delete(key)
        }
      } else {
        newParams.set(key, String(value))
      }

      return newParams
    }, { replace: true })
  }, [setSearchParams])

  // Toggle a value in an array filter (for multi-select checkboxes)
  const toggleFilterValue = useCallback(<K extends ArrayFilterKey>(
    key: K,
    value: string
  ) => {
    const currentValues = (filters[key] as string[] | undefined) || []
    const newValues = currentValues.includes(value)
      ? currentValues.filter(v => v !== value)
      : [...currentValues, value]
    setFilter(key, newValues.length > 0 ? newValues as ClientsFilters[K] : undefined)
  }, [filters, setFilter])

  // Apply a preset filter (replaces current filters)
  const applyPreset = useCallback((preset: FilterPreset) => {
    setSearchParams((prev) => {
      const newParams = new URLSearchParams()

      // Preserve search if present
      const search = prev.get('search')
      if (search) newParams.set('search', search)

      switch (preset) {
        case 'all':
          // Clear all filters
          break
        case 'connected':
          newParams.set('status', 'Connected')
          break
        case 'disconnected':
          newParams.set('status', 'Disconnected')
          break
        case 'wireless':
          newParams.set('type', 'Wireless')
          break
        case 'wired':
          newParams.set('type', 'Wired')
          break
        case 'health_good':
          newParams.set('health', 'Good')
          break
        case 'health_fair':
          newParams.set('health', 'Fair')
          break
        case 'health_poor':
          newParams.set('health', 'Poor')
          break
      }

      return newParams
    }, { replace: true })
  }, [setSearchParams])

  // Clear all filters
  const clearFilters = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true })
  }, [setSearchParams])

  // Check if a preset is currently active
  const isPresetActive = useCallback((preset: FilterPreset): boolean => {
    const onlyBasicFilters = !filters.site_id?.length && !filters.network?.length &&
      !filters.vlan?.length && !filters.role?.length && !filters.tunnel?.length &&
      !filters.auth?.length && !filters.key_mgmt?.length && !filters.connected_to?.length &&
      !filters.subnet

    switch (preset) {
      case 'all':
        return !hasFilters
      case 'connected':
        return filters.status?.length === 1 && filters.status[0] === 'Connected' && !filters.type && !filters.health && onlyBasicFilters
      case 'disconnected':
        return filters.status?.length === 1 && filters.status[0] === 'Disconnected' && !filters.type && !filters.health && onlyBasicFilters
      case 'wireless':
        return filters.type?.length === 1 && filters.type[0] === 'Wireless' && !filters.status && !filters.health && onlyBasicFilters
      case 'wired':
        return filters.type?.length === 1 && filters.type[0] === 'Wired' && !filters.status && !filters.health && onlyBasicFilters
      case 'health_good':
        return filters.health?.length === 1 && filters.health[0] === 'Good' && !filters.type && !filters.status && onlyBasicFilters
      case 'health_fair':
        return filters.health?.length === 1 && filters.health[0] === 'Fair' && !filters.type && !filters.status && onlyBasicFilters
      case 'health_poor':
        return filters.health?.length === 1 && filters.health[0] === 'Poor' && !filters.type && !filters.status && onlyBasicFilters
      default:
        return false
    }
  }, [filters, hasFilters])

  return {
    filters,
    hasFilters,
    activeFilterCount,
    filterSummary,
    setFilter,
    toggleFilterValue,
    applyPreset,
    clearFilters,
    isPresetActive,
  }
}

/**
 * Convert filters to API query params
 */
export function filtersToQueryParams(filters: ClientsFilters): Record<string, string> {
  const params: Record<string, string> = {}

  if (filters.type?.length) params.type = filters.type.join(',')
  if (filters.status?.length) params.status = filters.status.join(',')
  if (filters.health?.length) params.health = filters.health.join(',')
  if (filters.site_id?.length) params.site_id = filters.site_id.join(',')
  if (filters.network?.length) params.network = filters.network.join(',')
  if (filters.vlan?.length) params.vlan = filters.vlan.join(',')
  if (filters.role?.length) params.role = filters.role.join(',')
  if (filters.tunnel?.length) params.tunnel = filters.tunnel.join(',')
  if (filters.auth?.length) params.auth = filters.auth.join(',')
  if (filters.key_mgmt?.length) params.key_mgmt = filters.key_mgmt.join(',')
  if (filters.connected_to?.length) params.connected_to = filters.connected_to.join(',')
  if (filters.subnet) params.subnet = filters.subnet
  if (filters.search) params.search = filters.search

  return params
}
