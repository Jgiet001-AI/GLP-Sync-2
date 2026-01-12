import {
  X,
  Filter,
  ChevronDown,
  ChevronUp,
  Check,
  Wifi,
  Heart,
  Activity,
  Globe,
  Network,
  Shield,
  Key,
  Router,
  MapPin,
  Search,
} from 'lucide-react'
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ClientsFilters, ClientType, ClientStatus, ClientHealth } from '../../hooks/useClientsFilters'
import { clientsApiClient } from '../../api/client'

interface FilterSectionProps<T extends string> {
  title: string
  icon: React.ReactNode
  options: { value: T; label: string; color?: string }[]
  selected: T[]
  onToggle: (value: T) => void
  defaultOpen?: boolean
  searchable?: boolean
  maxHeight?: string
}

function FilterSection<T extends string>({
  title,
  icon,
  options,
  selected,
  onToggle,
  defaultOpen = false,
  searchable = false,
  maxHeight = 'max-h-48',
}: FilterSectionProps<T>) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const [searchTerm, setSearchTerm] = useState('')

  const filteredOptions = useMemo(() => {
    if (!searchTerm) return options
    const lower = searchTerm.toLowerCase()
    return options.filter(opt => opt.label.toLowerCase().includes(lower))
  }, [options, searchTerm])

  return (
    <div className="border-b border-slate-700/50 last:border-b-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-700/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          {icon}
          <span>{title}</span>
          {selected.length > 0 && (
            <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-xs text-violet-400">
              {selected.length}
            </span>
          )}
        </div>
        {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>

      {isOpen && (
        <div className="px-4 pb-3">
          {searchable && options.length > 5 && (
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800/50 py-1.5 pl-8 pr-3 text-xs text-white placeholder-slate-500 focus:border-violet-500 focus:outline-none"
              />
            </div>
          )}
          <div className={`space-y-0.5 overflow-y-auto ${maxHeight}`}>
            {filteredOptions.length === 0 ? (
              <p className="py-2 text-xs text-slate-500 text-center">No options found</p>
            ) : (
              filteredOptions.map((option) => {
                const isSelected = selected.includes(option.value)
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => onToggle(option.value)}
                    className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors ${
                      isSelected
                        ? 'bg-violet-500/20 text-violet-300'
                        : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-200'
                    }`}
                  >
                    <div
                      className={`flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center rounded border transition-colors ${
                        isSelected
                          ? 'border-violet-500 bg-violet-500'
                          : 'border-slate-600'
                      }`}
                    >
                      {isSelected && <Check className="h-2.5 w-2.5 text-white" />}
                    </div>
                    <span className="flex-1 text-left truncate">{option.label}</span>
                    {option.color && (
                      <span className={`h-2 w-2 rounded-full flex-shrink-0 ${option.color}`} />
                    )}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

interface ClientsFilterPanelProps {
  filters: ClientsFilters
  onToggle: (key: string, value: string) => void
  onClear: () => void
  onClose?: () => void
  className?: string
}

const typeOptions: { value: ClientType; label: string }[] = [
  { value: 'Wireless', label: 'Wireless' },
  { value: 'Wired', label: 'Wired' },
]

const statusOptions: { value: ClientStatus; label: string; color: string }[] = [
  { value: 'Connected', label: 'Connected', color: 'bg-emerald-500' },
  { value: 'Disconnected', label: 'Disconnected', color: 'bg-slate-500' },
  { value: 'Failed', label: 'Failed', color: 'bg-rose-500' },
  { value: 'Blocked', label: 'Blocked', color: 'bg-orange-500' },
]

const healthOptions: { value: ClientHealth; label: string; color: string }[] = [
  { value: 'Good', label: 'Good', color: 'bg-emerald-500' },
  { value: 'Fair', label: 'Fair', color: 'bg-amber-500' },
  { value: 'Poor', label: 'Poor', color: 'bg-rose-500' },
  { value: 'Unknown', label: 'Unknown', color: 'bg-slate-500' },
]

export function ClientsFilterPanel({
  filters,
  onToggle,
  onClear,
  onClose,
  className = '',
}: ClientsFilterPanelProps) {
  // Fetch dynamic filter options from API
  const { data: filterOptions } = useQuery({
    queryKey: ['client-filter-options'],
    queryFn: () => clientsApiClient.getFilterOptions(),
    staleTime: 60000, // 1 minute
  })

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
    return count
  }, [filters])

  // Convert API options to filter section format
  const siteOptions = useMemo(() =>
    filterOptions?.sites.map(s => ({ value: s.id, label: s.name || s.id })) || [],
    [filterOptions?.sites]
  )

  const networkOptions = useMemo(() =>
    filterOptions?.networks.map(n => ({ value: n, label: n })) || [],
    [filterOptions?.networks]
  )

  const vlanOptions = useMemo(() =>
    filterOptions?.vlans.map(v => ({ value: v, label: `VLAN ${v}` })) || [],
    [filterOptions?.vlans]
  )

  const roleOptions = useMemo(() =>
    filterOptions?.roles.map(r => ({ value: r, label: r })) || [],
    [filterOptions?.roles]
  )

  const tunnelOptions = useMemo(() =>
    filterOptions?.tunnels.map(t => ({ value: t, label: t })) || [],
    [filterOptions?.tunnels]
  )

  const authOptions = useMemo(() =>
    filterOptions?.authentications.map(a => ({ value: a, label: a })) || [],
    [filterOptions?.authentications]
  )

  const keyMgmtOptions = useMemo(() =>
    filterOptions?.key_managements.map(k => ({ value: k, label: k })) || [],
    [filterOptions?.key_managements]
  )

  const connectedToOptions = useMemo(() =>
    filterOptions?.connected_devices.map(d => ({ value: d, label: d })) || [],
    [filterOptions?.connected_devices]
  )

  const subnetOptions = useMemo(() =>
    filterOptions?.subnets.map(s => ({ value: s, label: s })) || [],
    [filterOptions?.subnets]
  )

  return (
    <div className={`rounded-xl border border-slate-700/50 bg-slate-800/50 backdrop-blur-sm ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-slate-400" />
          <h3 className="text-sm font-semibold text-white">Filters</h3>
          {activeFilterCount > 0 && (
            <span className="rounded-full bg-violet-500 px-2 py-0.5 text-xs text-white font-medium">
              {activeFilterCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeFilterCount > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
            >
              Clear all
            </button>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="flex items-center justify-center rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
              aria-label="Close filters"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Filter sections */}
      <div className="max-h-[calc(100vh-300px)] overflow-y-auto">
        {/* Basic Filters - Always Open */}
        <FilterSection
          title="Connection Type"
          icon={<Wifi className="h-4 w-4 text-slate-400" />}
          options={typeOptions}
          selected={filters.type || []}
          onToggle={(v) => onToggle('type', v)}
          defaultOpen={true}
        />

        <FilterSection
          title="Status"
          icon={<Activity className="h-4 w-4 text-slate-400" />}
          options={statusOptions}
          selected={filters.status || []}
          onToggle={(v) => onToggle('status', v)}
          defaultOpen={true}
        />

        <FilterSection
          title="Health"
          icon={<Heart className="h-4 w-4 text-slate-400" />}
          options={healthOptions}
          selected={filters.health || []}
          onToggle={(v) => onToggle('health', v)}
          defaultOpen={true}
        />

        {/* Network Filters */}
        {siteOptions.length > 0 && (
          <FilterSection
            title="Site"
            icon={<MapPin className="h-4 w-4 text-slate-400" />}
            options={siteOptions}
            selected={filters.site_id || []}
            onToggle={(v) => onToggle('site_id', v)}
            searchable
          />
        )}

        {networkOptions.length > 0 && (
          <FilterSection
            title="Network (SSID)"
            icon={<Globe className="h-4 w-4 text-slate-400" />}
            options={networkOptions}
            selected={filters.network || []}
            onToggle={(v) => onToggle('network', v)}
            searchable
          />
        )}

        {vlanOptions.length > 0 && (
          <FilterSection
            title="VLAN"
            icon={<Network className="h-4 w-4 text-slate-400" />}
            options={vlanOptions}
            selected={filters.vlan || []}
            onToggle={(v) => onToggle('vlan', v)}
            searchable
          />
        )}

        {subnetOptions.length > 0 && (
          <FilterSection
            title="Subnet"
            icon={<Network className="h-4 w-4 text-slate-400" />}
            options={subnetOptions}
            selected={filters.subnet ? [filters.subnet] : []}
            onToggle={(v) => onToggle('subnet', v)}
            searchable
          />
        )}

        {/* Device Filters */}
        {connectedToOptions.length > 0 && (
          <FilterSection
            title="Connected To"
            icon={<Router className="h-4 w-4 text-slate-400" />}
            options={connectedToOptions}
            selected={filters.connected_to || []}
            onToggle={(v) => onToggle('connected_to', v)}
            searchable
            maxHeight="max-h-64"
          />
        )}

        {roleOptions.length > 0 && (
          <FilterSection
            title="Role"
            icon={<Shield className="h-4 w-4 text-slate-400" />}
            options={roleOptions}
            selected={filters.role || []}
            onToggle={(v) => onToggle('role', v)}
            searchable
          />
        )}

        {/* Security Filters */}
        {tunnelOptions.length > 0 && (
          <FilterSection
            title="Tunnel"
            icon={<Network className="h-4 w-4 text-slate-400" />}
            options={tunnelOptions}
            selected={filters.tunnel || []}
            onToggle={(v) => onToggle('tunnel', v)}
          />
        )}

        {authOptions.length > 0 && (
          <FilterSection
            title="Authentication"
            icon={<Shield className="h-4 w-4 text-slate-400" />}
            options={authOptions}
            selected={filters.auth || []}
            onToggle={(v) => onToggle('auth', v)}
            searchable
          />
        )}

        {keyMgmtOptions.length > 0 && (
          <FilterSection
            title="Key Management"
            icon={<Key className="h-4 w-4 text-slate-400" />}
            options={keyMgmtOptions}
            selected={filters.key_mgmt || []}
            onToggle={(v) => onToggle('key_mgmt', v)}
            searchable
          />
        )}
      </div>
    </div>
  )
}

/**
 * Compact horizontal filter bar for inline display
 */
export function ClientsFilterBar({
  filters,
  activeFilterCount,
  onClear,
  className = '',
}: {
  filters: ClientsFilters
  activeFilterCount: number
  onClear: () => void
  className?: string
}) {
  const chips: { key: string; label: string; color: string }[] = []

  if (filters.type?.length) {
    filters.type.forEach(t => {
      chips.push({
        key: `type-${t}`,
        label: t,
        color: t === 'Wireless' ? 'bg-violet-500/20 text-violet-400 border-violet-500/30' : 'bg-sky-500/20 text-sky-400 border-sky-500/30',
      })
    })
  }

  if (filters.status?.length) {
    filters.status.forEach(s => {
      const colorMap: Record<string, string> = {
        Connected: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
        Disconnected: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
        Failed: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
        Blocked: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
      }
      chips.push({
        key: `status-${s}`,
        label: s,
        color: colorMap[s] || 'bg-slate-500/20 text-slate-400 border-slate-500/30',
      })
    })
  }

  if (filters.health?.length) {
    filters.health.forEach(h => {
      const colorMap: Record<string, string> = {
        Good: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
        Fair: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
        Poor: 'bg-rose-500/20 text-rose-400 border-rose-500/30',
        Unknown: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
      }
      chips.push({
        key: `health-${h}`,
        label: `Health: ${h}`,
        color: colorMap[h] || 'bg-slate-500/20 text-slate-400 border-slate-500/30',
      })
    })
  }

  // Add other filters as generic chips
  if (filters.site_id?.length) {
    chips.push({ key: 'sites', label: `${filters.site_id.length} Sites`, color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' })
  }
  if (filters.network?.length) {
    chips.push({ key: 'networks', label: `${filters.network.length} Networks`, color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' })
  }
  if (filters.vlan?.length) {
    chips.push({ key: 'vlans', label: `${filters.vlan.length} VLANs`, color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' })
  }
  if (filters.role?.length) {
    chips.push({ key: 'roles', label: `${filters.role.length} Roles`, color: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30' })
  }
  if (filters.tunnel?.length) {
    chips.push({ key: 'tunnels', label: filters.tunnel.join(', '), color: 'bg-teal-500/20 text-teal-400 border-teal-500/30' })
  }
  if (filters.connected_to?.length) {
    chips.push({ key: 'devices', label: `${filters.connected_to.length} Devices`, color: 'bg-pink-500/20 text-pink-400 border-pink-500/30' })
  }
  if (filters.auth?.length) {
    chips.push({ key: 'auth', label: `${filters.auth.length} Auth Types`, color: 'bg-lime-500/20 text-lime-400 border-lime-500/30' })
  }
  if (filters.key_mgmt?.length) {
    chips.push({ key: 'keymgmt', label: `${filters.key_mgmt.length} Key Mgmt`, color: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' })
  }
  if (filters.subnet) {
    chips.push({ key: 'subnet', label: `Subnet: ${filters.subnet}`, color: 'bg-orange-500/20 text-orange-400 border-orange-500/30' })
  }

  if (chips.length === 0) return null

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
        Active Filters ({activeFilterCount}):
      </span>
      {chips.slice(0, 6).map(chip => (
        <span
          key={chip.key}
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${chip.color}`}
        >
          {chip.label}
        </span>
      ))}
      {chips.length > 6 && (
        <span className="text-xs text-slate-400">+{chips.length - 6} more</span>
      )}
      <button
        type="button"
        onClick={onClear}
        className="flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-slate-400 hover:bg-slate-700/50 hover:text-white transition-colors"
      >
        <X className="h-3 w-3" />
        Clear all
      </button>
    </div>
  )
}
