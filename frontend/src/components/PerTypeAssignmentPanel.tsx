import { Globe, CheckCircle } from 'lucide-react'
import clsx from 'clsx'
import { TypeGroupCard } from './TypeGroupCard'
import type { DeviceAssignment, OptionsResponse, TypeAssignmentConfig } from '../types'

interface DeviceTypeGroup {
  deviceType: string
  model: string | null
  groupKey: string
  displayName: string
  devices: DeviceAssignment[]
  compatibleSubscriptions: import('../types').Subscription[]
}

interface PerTypeAssignmentPanelProps {
  deviceGroups: DeviceTypeGroup[]
  typeConfigs: Map<string, TypeAssignmentConfig>
  globalApplicationId: string
  options: OptionsResponse | null
  selectedCount: number
  isLoading: boolean
  onGlobalApplicationChange: (id: string) => void
  onTypeConfigChange: (deviceType: string, updates: Partial<TypeAssignmentConfig>) => void
  onApplyAll: () => void
}

export function PerTypeAssignmentPanel({
  deviceGroups,
  typeConfigs,
  globalApplicationId,
  options,
  selectedCount,
  isLoading,
  onGlobalApplicationChange,
  onTypeConfigChange,
  onApplyAll,
}: PerTypeAssignmentPanelProps) {
  if (!options) {
    return (
      <div className="space-y-4" data-testid="assignment-panel-loading">
        <div className="animate-pulse">
          <div className="h-6 bg-slate-700 rounded w-1/3 mb-4" />
          <div className="space-y-3">
            <div className="h-24 bg-slate-700 rounded" />
            <div className="h-24 bg-slate-700 rounded" />
            <div className="h-24 bg-slate-700 rounded" />
          </div>
        </div>
      </div>
    )
  }

  // Count how many types have subscriptions selected
  const typesWithSubscriptions = Array.from(typeConfigs.values())
    .filter(c => c.selectedSubscriptionId).length
  const totalTypes = deviceGroups.length

  return (
    <div className="space-y-6" data-testid="per-type-assignment-panel">
      {/* Selected devices info */}
      <div className="bg-hpe-green/10 border border-hpe-green/20 rounded-lg p-4">
        <p className="text-hpe-green font-medium">
          {selectedCount} device{selectedCount !== 1 ? 's' : ''} selected
        </p>
        <p className="text-sm text-slate-400 mt-1">
          Grouped into {totalTypes} device type{totalTypes !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Global Region Section */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4">
        <div className="flex items-center gap-2 mb-4">
          <div className="p-2 rounded-lg bg-hpe-blue/20">
            <Globe className="w-5 h-5 text-hpe-blue" aria-hidden="true" />
          </div>
          <div>
            <h3 className="font-medium text-slate-200">Region (Global)</h3>
            <p className="text-sm text-slate-400">Applies to all device types</p>
          </div>
        </div>

        <label htmlFor="global-region" className="sr-only">Select a region</label>
        <select
          id="global-region"
          value={globalApplicationId}
          onChange={(e) => onGlobalApplicationChange(e.target.value)}
          className="input w-full"
          disabled={isLoading}
          data-testid="global-region-select"
        >
          <option value="">Select a region...</option>
          {options.regions.map((region) => (
            <option key={region.application_id} value={region.application_id}>
              {region.display_name}
            </option>
          ))}
        </select>
      </div>

      {/* Per-Type Assignment Cards */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider">
          Per-Type Assignments
        </h3>

        {deviceGroups.length === 0 ? (
          <div className="text-center text-slate-400 py-8">
            No devices selected
          </div>
        ) : (
          deviceGroups.map((group) => (
            <TypeGroupCard
              key={group.groupKey}
              deviceType={group.displayName}
              deviceCount={group.devices.length}
              compatibleSubscriptions={group.compatibleSubscriptions}
              config={typeConfigs.get(group.groupKey) ?? {
                deviceType: group.groupKey,
                deviceCount: group.devices.length,
                selectedSubscriptionId: null,
                selectedTags: {},
                pendingTagKey: '',
                pendingTagValue: '',
              }}
              existingTags={options.existing_tags}
              onConfigChange={(updates) => onTypeConfigChange(group.groupKey, updates)}
            />
          ))
        )}
      </div>

      {/* Summary and Apply Button */}
      <div className="border-t border-slate-700/50 pt-4">
        {/* Assignment Summary */}
        <div className="flex items-center gap-4 mb-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Region:</span>
            {globalApplicationId ? (
              <span className="flex items-center gap-1 text-hpe-green">
                <CheckCircle className="w-4 h-4" />
                Selected
              </span>
            ) : (
              <span className="text-amber-400 font-medium">Required - Select Above</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Subscriptions:</span>
            <span className={clsx(
              typesWithSubscriptions === totalTypes ? 'text-hpe-green' : 'text-amber-400'
            )}>
              {typesWithSubscriptions} / {totalTypes} types
            </span>
          </div>
        </div>

        {/* Warning when region not selected */}
        {!globalApplicationId && typesWithSubscriptions > 0 && (
          <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
            <p className="text-sm text-amber-400">
              <span className="font-medium">Region Required:</span> GreenLake requires
              a region to be assigned before subscriptions can be applied.
            </p>
          </div>
        )}

        {/* Apply Button */}
        <button
          onClick={onApplyAll}
          disabled={selectedCount === 0 || isLoading || !globalApplicationId}
          className={clsx(
            'btn w-full',
            selectedCount > 0 && !isLoading && globalApplicationId
              ? 'btn-primary'
              : 'btn-secondary opacity-50 cursor-not-allowed'
          )}
          data-testid="apply-all-btn"
        >
          {isLoading ? 'Applying...' : !globalApplicationId ? 'Select Region First' : 'Apply All Assignments'}
        </button>
      </div>
    </div>
  )
}
