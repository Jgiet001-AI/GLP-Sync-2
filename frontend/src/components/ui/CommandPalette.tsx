import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { dashboardApiClient } from '../../api/client'
import type { DeviceListItem } from '../../types'
import {
  Search,
  Server,
  Shield,
  Wifi,
  Router,
  HardDrive,
  LayoutDashboard,
  Upload,
  ArrowRight,
  Command,
} from 'lucide-react'

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
}

// Device type icons
const deviceIcons: Record<string, typeof Server> = {
  AP: Wifi,
  SWITCH: Router,
  GATEWAY: Router,
  IAP: Wifi,
  COMPUTE: Server,
  STORAGE: HardDrive,
  UNKNOWN: Server,
}

// Quick navigation items
const quickNavItems = [
  { label: 'Dashboard', path: '/', icon: LayoutDashboard, keywords: ['home', 'overview', 'stats'] },
  { label: 'Devices', path: '/devices', icon: Server, keywords: ['device', 'serial', 'mac'] },
  { label: 'Subscriptions', path: '/subscriptions', icon: Shield, keywords: ['license', 'subscription', 'key'] },
  { label: 'Assignment', path: '/assignment', icon: Upload, keywords: ['assign', 'upload', 'bulk'] },
]

export function CommandPalette({ open, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  // Search devices when query is long enough
  const { data: searchResults, isLoading } = useQuery({
    queryKey: ['device-search', query],
    queryFn: () => dashboardApiClient.searchDevices(query, 5),
    enabled: query.length >= 2,
    staleTime: 10000,
  })

  // Filter quick nav items based on query
  const filteredNavItems = quickNavItems.filter((item) => {
    if (!query) return true
    const lowerQuery = query.toLowerCase()
    return (
      item.label.toLowerCase().includes(lowerQuery) ||
      item.keywords.some((k) => k.includes(lowerQuery))
    )
  })

  // Combine results
  const allResults: Array<
    | (typeof quickNavItems[number] & { type: 'nav' })
    | (DeviceListItem & { type: 'device' })
  > = [
    ...filteredNavItems.map((item) => ({
      type: 'nav' as const,
      ...item,
    })),
    ...(searchResults?.items || []).map((device: DeviceListItem) => ({
      type: 'device' as const,
      ...device,
    })),
  ]

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  // Focus input when opened
  useEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus()
    }
  }, [open])

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuery('')
      setSelectedIndex(0)
    }
  }, [open])

  // Handle keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex((prev) => Math.min(prev + 1, allResults.length - 1))
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex((prev) => Math.max(prev - 1, 0))
          break
        case 'Enter':
          e.preventDefault()
          const selected = allResults[selectedIndex]
          if (selected) {
            if (selected.type === 'nav') {
              navigate(selected.path)
            } else {
              navigate(`/devices?search=${selected.serial_number}`)
            }
            onClose()
          }
          break
        case 'Escape':
          onClose()
          break
      }
    },
    [allResults, selectedIndex, navigate, onClose]
  )

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/80 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Command palette */}
      <div className="fixed left-1/2 top-[20%] w-full max-w-xl -translate-x-1/2 transform px-4">
        <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-800 shadow-2xl">
          {/* Search input */}
          <div className="relative border-b border-slate-700">
            <Search className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-slate-400" />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search devices, pages, or type a command..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="w-full bg-transparent py-4 pl-12 pr-12 text-white placeholder-slate-400 focus:outline-none"
            />
            <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-1">
              <kbd className="rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-400">esc</kbd>
            </div>
          </div>

          {/* Results */}
          <div className="max-h-80 overflow-y-auto">
            {/* Quick navigation */}
            {filteredNavItems.length > 0 && (
              <div className="p-2">
                <p className="px-2 py-1 text-xs font-medium uppercase tracking-wider text-slate-500">
                  Quick Navigation
                </p>
                {filteredNavItems.map((item, idx) => {
                  const Icon = item.icon
                  const isSelected = idx === selectedIndex
                  return (
                    <button
                      key={item.path}
                      onClick={() => {
                        navigate(item.path)
                        onClose()
                      }}
                      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                        isSelected
                          ? 'bg-hpe-green/10 text-hpe-green'
                          : 'text-slate-300 hover:bg-slate-700'
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      <span className="flex-1">{item.label}</span>
                      <ArrowRight className="h-4 w-4 text-slate-500" />
                    </button>
                  )
                })}
              </div>
            )}

            {/* Device search results */}
            {query.length >= 2 && (
              <div className="border-t border-slate-700 p-2">
                <p className="px-2 py-1 text-xs font-medium uppercase tracking-wider text-slate-500">
                  Devices
                </p>
                {isLoading ? (
                  <div className="flex items-center gap-2 px-3 py-4 text-slate-400">
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-600 border-t-slate-400" />
                    Searching...
                  </div>
                ) : searchResults?.items.length === 0 ? (
                  <p className="px-3 py-4 text-sm text-slate-500">No devices found</p>
                ) : (
                  searchResults?.items.map((device, idx) => {
                    const resultIdx = filteredNavItems.length + idx
                    const isSelected = resultIdx === selectedIndex
                    const Icon = deviceIcons[device.device_type || 'UNKNOWN'] || Server
                    return (
                      <button
                        key={device.id}
                        onClick={() => {
                          navigate(`/devices?search=${device.serial_number}`)
                          onClose()
                        }}
                        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors ${
                          isSelected
                            ? 'bg-sky-500/10 text-sky-400'
                            : 'text-slate-300 hover:bg-slate-700'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        <div className="flex-1 min-w-0">
                          <p className="font-mono text-sm">{device.serial_number}</p>
                          <p className="truncate text-xs text-slate-500">
                            {device.device_type} · {device.mac_address || 'No MAC'}
                          </p>
                        </div>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${
                            device.assigned_state === 'ASSIGNED_TO_SERVICE'
                              ? 'bg-emerald-500/10 text-emerald-400'
                              : 'bg-amber-500/10 text-amber-400'
                          }`}
                        >
                          {device.assigned_state === 'ASSIGNED_TO_SERVICE' ? 'Assigned' : 'Unassigned'}
                        </span>
                      </button>
                    )
                  })
                )}
              </div>
            )}

            {/* Empty state */}
            {query.length > 0 && query.length < 2 && (
              <div className="p-6 text-center text-slate-500">
                <p className="text-sm">Type at least 2 characters to search devices</p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="border-t border-slate-700 bg-slate-800/50 px-4 py-2">
            <div className="flex items-center justify-between text-xs text-slate-500">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <kbd className="rounded bg-slate-700 px-1 py-0.5">↑</kbd>
                  <kbd className="rounded bg-slate-700 px-1 py-0.5">↓</kbd>
                  navigate
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="rounded bg-slate-700 px-1.5 py-0.5">↵</kbd>
                  select
                </span>
              </div>
              <span className="flex items-center gap-1">
                <Command className="h-3 w-3" />K to open
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
