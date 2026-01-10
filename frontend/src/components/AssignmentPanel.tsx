import { useState } from 'react'
import { Tag, Layers, Globe, Plus, X } from 'lucide-react'
import clsx from 'clsx'
import type { DeviceAssignment, OptionsResponse, Region, Subscription } from '../types'

interface AssignmentPanelProps {
  options: OptionsResponse | null
  selectedCount: number
  onApplyToSelected: (updates: Partial<DeviceAssignment>) => void
  isLoading: boolean
}

export function AssignmentPanel({
  options,
  selectedCount,
  onApplyToSelected,
  isLoading,
}: AssignmentPanelProps) {
  const [selectedSubscription, setSelectedSubscription] = useState<string>('')
  const [selectedRegion, setSelectedRegion] = useState<string>('')
  const [tagKey, setTagKey] = useState('')
  const [tagValue, setTagValue] = useState('')
  const [pendingTags, setPendingTags] = useState<Record<string, string>>({})

  if (!options) {
    return (
      <div className="card" data-testid="assignment-panel-loading">
        <div className="animate-pulse">
          <div className="h-6 bg-slate-700 rounded w-1/3 mb-4" />
          <div className="space-y-3">
            <div className="h-10 bg-slate-700 rounded" />
            <div className="h-10 bg-slate-700 rounded" />
            <div className="h-10 bg-slate-700 rounded" />
          </div>
        </div>
      </div>
    )
  }

  const handleApplySubscription = () => {
    if (selectedSubscription) {
      onApplyToSelected({
        selected_subscription_id: selectedSubscription,
      })
    }
  }

  const handleApplyRegion = () => {
    if (selectedRegion) {
      onApplyToSelected({
        selected_application_id: selectedRegion,
      })
    }
  }

  const handleAddTag = () => {
    if (tagKey && tagValue) {
      setPendingTags((prev) => ({ ...prev, [tagKey]: tagValue }))
      setTagKey('')
      setTagValue('')
    }
  }

  const handleRemoveTag = (key: string) => {
    setPendingTags((prev) => {
      const next = { ...prev }
      delete next[key]
      return next
    })
  }

  const handleApplyTags = () => {
    if (Object.keys(pendingTags).length > 0) {
      onApplyToSelected({
        selected_tags: pendingTags,
      })
    }
  }

  const formatDaysRemaining = (days: number | null) => {
    if (days === null) return ''
    if (days < 30) return ` (${days}d remaining)`
    if (days < 365) return ` (${Math.floor(days / 30)}mo remaining)`
    return ` (${Math.floor(days / 365)}y remaining)`
  }

  return (
    <div className="space-y-6" data-testid="assignment-panel">
      {/* Selected devices info */}
      <div className="bg-hpe-green/10 border border-hpe-green/20 rounded-lg p-4">
        <p className="text-hpe-green font-medium">
          {selectedCount} device{selectedCount !== 1 ? 's' : ''} selected
        </p>
        <p className="text-sm text-slate-400 mt-1">
          Apply assignments to all selected devices
        </p>
      </div>

      {/* Subscription */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-5 h-5 text-hpe-purple" aria-hidden="true" />
          <h3 className="font-medium text-slate-200">Subscription</h3>
        </div>

        <label htmlFor="subscription-select" className="sr-only">Select a subscription</label>
        <select
          id="subscription-select"
          value={selectedSubscription}
          onChange={(e) => setSelectedSubscription(e.target.value)}
          className="input w-full mb-3"
          disabled={isLoading}
          data-testid="subscription-select"
        >
          <option value="">Select a subscription...</option>
          {options.subscriptions.map((sub: Subscription) => (
            <option key={sub.id} value={sub.id}>
              {sub.key} - {sub.tier} ({sub.available_quantity} available)
              {formatDaysRemaining(sub.days_remaining)}
            </option>
          ))}
        </select>

        <button
          onClick={handleApplySubscription}
          disabled={!selectedSubscription || selectedCount === 0}
          className={clsx(
            'btn w-full',
            selectedSubscription && selectedCount > 0
              ? 'btn-primary'
              : 'btn-secondary opacity-50 cursor-not-allowed'
          )}
          data-testid="apply-subscription-btn"
        >
          Apply Subscription
        </button>
      </div>

      {/* Region (Application) */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Globe className="w-5 h-5 text-hpe-blue" aria-hidden="true" />
          <h3 className="font-medium text-slate-200">Region</h3>
        </div>

        <label htmlFor="region-select" className="sr-only">Select a region</label>
        <select
          id="region-select"
          value={selectedRegion}
          onChange={(e) => setSelectedRegion(e.target.value)}
          className="input w-full mb-3"
          disabled={isLoading}
          data-testid="region-select"
        >
          <option value="">Select a region...</option>
          {options.regions.map((region: Region) => (
            <option key={region.application_id} value={region.application_id}>
              {region.display_name}
            </option>
          ))}
        </select>

        <button
          onClick={handleApplyRegion}
          disabled={!selectedRegion || selectedCount === 0}
          className={clsx(
            'btn w-full',
            selectedRegion && selectedCount > 0
              ? 'btn-primary'
              : 'btn-secondary opacity-50 cursor-not-allowed'
          )}
          data-testid="apply-region-btn"
        >
          Apply Region
        </button>
      </div>

      {/* Tags */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Tag className="w-5 h-5 text-hpe-orange" aria-hidden="true" />
          <h3 className="font-medium text-slate-200">Tags</h3>
        </div>

        {/* Existing tags to apply */}
        {Object.keys(pendingTags).length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4" data-testid="pending-tags">
            {Object.entries(pendingTags).map(([key, value]) => (
              <span
                key={key}
                className="inline-flex items-center gap-1 px-3 py-1 bg-slate-700 rounded-full text-sm text-slate-200"
              >
                <span className="font-medium">{key}:</span>
                <span>{value}</span>
                <button
                  onClick={() => handleRemoveTag(key)}
                  className="ml-1 text-slate-400 hover:text-rose-400"
                  aria-label={`Remove tag ${key}`}
                  data-testid={`remove-tag-${key}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Add new tag */}
        <div className="flex gap-2 mb-3">
          <div className="flex-1">
            <label htmlFor="tag-key" className="sr-only">Tag key</label>
            <input
              id="tag-key"
              type="text"
              value={tagKey}
              onChange={(e) => setTagKey(e.target.value)}
              placeholder="Key"
              className="input w-full"
              list="tag-keys"
              data-testid="tag-key-input"
            />
            <datalist id="tag-keys">
              {[...new Set(options.existing_tags.map((t) => t.key))].map((key) => (
                <option key={key} value={key} />
              ))}
            </datalist>
          </div>
          <div className="flex-1">
            <label htmlFor="tag-value" className="sr-only">Tag value</label>
            <input
              id="tag-value"
              type="text"
              value={tagValue}
              onChange={(e) => setTagValue(e.target.value)}
              placeholder="Value"
              className="input w-full"
              list="tag-values"
              data-testid="tag-value-input"
            />
            <datalist id="tag-values">
              {[...new Set(
                options.existing_tags
                  .filter((t) => t.key === tagKey)
                  .map((t) => t.value)
              )].map((value) => (
                <option key={value} value={value} />
              ))}
            </datalist>
          </div>
          <button
            onClick={handleAddTag}
            disabled={!tagKey || !tagValue}
            className="btn btn-secondary"
            aria-label="Add tag"
            data-testid="add-tag-btn"
          >
            <Plus className="w-5 h-5" />
          </button>
        </div>

        <button
          onClick={handleApplyTags}
          disabled={Object.keys(pendingTags).length === 0 || selectedCount === 0}
          className={clsx(
            'btn w-full',
            Object.keys(pendingTags).length > 0 && selectedCount > 0
              ? 'btn-primary'
              : 'btn-secondary opacity-50 cursor-not-allowed'
          )}
          data-testid="apply-tags-btn"
        >
          Apply Tags
        </button>
      </div>
    </div>
  )
}
