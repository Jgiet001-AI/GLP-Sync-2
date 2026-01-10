import { Layers, Tag, Plus, X, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { Subscription, TypeAssignmentConfig, Tag as TagType } from '../types'

interface TypeGroupCardProps {
  deviceType: string
  deviceCount: number
  compatibleSubscriptions: Subscription[]
  config: TypeAssignmentConfig
  existingTags: TagType[]
  onConfigChange: (updates: Partial<TypeAssignmentConfig>) => void
}

export function TypeGroupCard({
  deviceType,
  deviceCount,
  compatibleSubscriptions,
  config,
  existingTags,
  onConfigChange,
}: TypeGroupCardProps) {
  const formatDaysRemaining = (days: number | null) => {
    if (days === null) return ''
    if (days < 30) return ` (${days}d remaining)`
    if (days < 365) return ` (${Math.floor(days / 30)}mo remaining)`
    return ` (${Math.floor(days / 365)}y remaining)`
  }

  const handleAddTag = () => {
    console.log('handleAddTag called', { pendingTagKey: config.pendingTagKey, pendingTagValue: config.pendingTagValue })
    if (config.pendingTagKey && config.pendingTagValue) {
      console.log('Adding tag:', config.pendingTagKey, '=', config.pendingTagValue)
      onConfigChange({
        selectedTags: {
          ...config.selectedTags,
          [config.pendingTagKey]: config.pendingTagValue,
        },
        pendingTagKey: '',
        pendingTagValue: '',
      })
    } else {
      console.log('Tag not added - key or value empty')
    }
  }

  const handleRemoveTag = (key: string) => {
    const newTags = { ...config.selectedTags }
    delete newTags[key]
    onConfigChange({ selectedTags: newTags })
  }

  const isUnknownType = deviceType === 'Unknown'

  // Get unique tag keys for autocomplete
  const uniqueTagKeys = [...new Set(existingTags.map(t => t.key))]
  const uniqueTagValues = [...new Set(
    existingTags
      .filter(t => t.key === config.pendingTagKey)
      .map(t => t.value)
  )]

  return (
    <div
      className="rounded-xl border border-slate-700/50 bg-slate-800/30 p-4"
      data-testid={`type-group-${deviceType}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={clsx(
            'p-2 rounded-lg',
            isUnknownType ? 'bg-amber-500/20' : 'bg-hpe-green/20'
          )}>
            <Layers className={clsx(
              'w-5 h-5',
              isUnknownType ? 'text-amber-400' : 'text-hpe-green'
            )} aria-hidden="true" />
          </div>
          <div>
            <h3 className="font-medium text-slate-200">{deviceType}</h3>
            <p className="text-sm text-slate-400">{deviceCount} device{deviceCount !== 1 ? 's' : ''}</p>
          </div>
        </div>
      </div>

      {/* Subscription Section */}
      <div className="mb-4">
        <label
          htmlFor={`subscription-${deviceType}`}
          className="block text-sm font-medium text-slate-300 mb-2"
        >
          Subscription
        </label>

        {isUnknownType ? (
          <div className="flex items-center gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span>Devices not in database - cannot assign subscription</span>
          </div>
        ) : compatibleSubscriptions.length === 0 ? (
          <div className="flex items-center gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" aria-hidden="true" />
            <span>No compatible subscriptions available for {deviceType}</span>
          </div>
        ) : (
          <select
            id={`subscription-${deviceType}`}
            value={config.selectedSubscriptionId || ''}
            onChange={(e) => onConfigChange({ selectedSubscriptionId: e.target.value || null })}
            className="input w-full"
            data-testid={`subscription-select-${deviceType}`}
          >
            <option value="">Select subscription...</option>
            {compatibleSubscriptions.map((sub) => (
              <option key={sub.id} value={sub.id}>
                {sub.key} - {sub.tier} ({sub.available_quantity} available)
                {formatDaysRemaining(sub.days_remaining)}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Tags Section */}
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-2">
          <Tag className="w-4 h-4 inline mr-1" aria-hidden="true" />
          Tags
        </label>

        {/* Pending tags display */}
        {Object.keys(config.selectedTags).length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3" data-testid={`tags-${deviceType}`}>
            {Object.entries(config.selectedTags).map(([key, value]) => (
              <span
                key={key}
                className="inline-flex items-center gap-1 px-2 py-1 bg-slate-700 rounded-full text-xs text-slate-200"
              >
                <span className="font-medium">{key}:</span>
                <span>{value}</span>
                <button
                  onClick={() => handleRemoveTag(key)}
                  className="ml-1 text-slate-400 hover:text-rose-400"
                  aria-label={`Remove tag ${key}`}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        {/* Add tag inputs */}
        <div className="flex gap-2">
          <div className="flex-1">
            <input
              type="text"
              value={config.pendingTagKey}
              onChange={(e) => {
                console.log('Tag key changed:', e.target.value)
                onConfigChange({ pendingTagKey: e.target.value })
              }}
              placeholder="Key"
              className="input w-full text-sm"
              list={`tag-keys-${deviceType}`}
              data-testid={`tag-key-${deviceType}`}
            />
            <datalist id={`tag-keys-${deviceType}`}>
              {uniqueTagKeys.map((key) => (
                <option key={key} value={key} />
              ))}
            </datalist>
          </div>
          <div className="flex-1">
            <input
              type="text"
              value={config.pendingTagValue}
              onChange={(e) => onConfigChange({ pendingTagValue: e.target.value })}
              placeholder="Value"
              className="input w-full text-sm"
              list={`tag-values-${deviceType}`}
              data-testid={`tag-value-${deviceType}`}
            />
            <datalist id={`tag-values-${deviceType}`}>
              {uniqueTagValues.map((value) => (
                <option key={value} value={value} />
              ))}
            </datalist>
          </div>
          <button
            onClick={handleAddTag}
            disabled={!config.pendingTagKey || !config.pendingTagValue}
            className="btn btn-secondary px-3"
            aria-label="Add tag"
            data-testid={`add-tag-${deviceType}`}
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
