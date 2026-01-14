import { useState } from 'react'
import { Layers, SortAsc, Plus, X, ArrowUp, ArrowDown } from 'lucide-react'
import clsx from 'clsx'
import type { GroupingConfig, SortingConfig, SortDirection, TableMetadata } from '../../types'

interface GroupingPanelProps {
  tables: TableMetadata[]
  grouping: GroupingConfig[]
  sorting: SortingConfig[]
  onAddGrouping: (field: string, table?: string | null) => void
  onRemoveGrouping: (index: number) => void
  onAddSorting: (field: string, direction: SortDirection, table?: string | null) => void
  onRemoveSorting: (index: number) => void
  onUpdateSorting: (index: number, updates: Partial<SortingConfig>) => void
  isLoading?: boolean
}

export function GroupingPanel({
  tables,
  grouping,
  sorting,
  onAddGrouping,
  onRemoveGrouping,
  onAddSorting,
  onRemoveSorting,
  onUpdateSorting,
  isLoading = false,
}: GroupingPanelProps) {
  const [selectedGroupField, setSelectedGroupField] = useState('')
  const [selectedSortField, setSelectedSortField] = useState('')
  const [selectedSortDirection, setSelectedSortDirection] = useState<SortDirection>('ASC')

  const handleAddGrouping = () => {
    if (selectedGroupField) {
      const [table, field] = selectedGroupField.split('.')
      onAddGrouping(field, table)
      setSelectedGroupField('')
    }
  }

  const handleAddSorting = () => {
    if (selectedSortField) {
      const [table, field] = selectedSortField.split('.')
      onAddSorting(field, selectedSortDirection, table)
      setSelectedSortField('')
      setSelectedSortDirection('ASC')
    }
  }

  const toggleSortDirection = (index: number) => {
    const currentDirection = sorting[index].direction
    onUpdateSorting(index, { direction: currentDirection === 'ASC' ? 'DESC' : 'ASC' })
  }

  // Get display name for a field
  const getFieldDisplayName = (table: string | null, field: string): string => {
    const tableObj = tables.find((t) => t.table_name === table)
    if (!tableObj) return field

    const fieldObj = tableObj.fields.find((f) => f.field_name === field)
    return fieldObj?.display_name || field
  }

  if (isLoading) {
    return (
      <div className="card" data-testid="grouping-panel-loading">
        <div className="animate-pulse">
          <div className="h-6 bg-slate-700 rounded w-1/3 mb-4" />
          <div className="space-y-3">
            <div className="h-10 bg-slate-700 rounded" />
            <div className="h-10 bg-slate-700 rounded" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6" data-testid="grouping-panel">
      {/* Grouping Section */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Layers className="w-5 h-5 text-hpe-purple" aria-hidden="true" />
          <h3 className="font-medium text-slate-200">Group By</h3>
        </div>

        <p className="text-sm text-slate-400 mb-4">
          Group results by one or more fields to see aggregated data.
        </p>

        {/* Current grouping fields */}
        {grouping.length > 0 && (
          <div className="mb-4 space-y-2" data-testid="current-grouping">
            {grouping.map((group, index) => (
              <div
                key={index}
                className="flex items-center justify-between bg-slate-700/50 rounded-lg px-3 py-2 group hover:bg-slate-700 transition-colors"
                data-testid={`grouping-item-${index}`}
              >
                <div className="flex items-center gap-2">
                  <Layers className="w-4 h-4 text-hpe-purple" aria-hidden="true" />
                  <span className="text-sm text-slate-200">
                    {group.table && (
                      <span className="text-slate-400">{group.table}.</span>
                    )}
                    {getFieldDisplayName(group.table, group.field)}
                  </span>
                </div>
                <button
                  onClick={() => onRemoveGrouping(index)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-rose-400"
                  aria-label={`Remove grouping ${group.field}`}
                  data-testid={`remove-grouping-${index}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Add grouping field */}
        <div className="space-y-3">
          <label htmlFor="group-field-select" className="sr-only">
            Select field to group by
          </label>
          <select
            id="group-field-select"
            value={selectedGroupField}
            onChange={(e) => setSelectedGroupField(e.target.value)}
            className="input w-full"
            disabled={isLoading}
            data-testid="group-field-select"
          >
            <option value="">Select a field to group by...</option>
            {tables.map((table) => (
              <optgroup key={table.table_name} label={table.display_name}>
                {table.fields.map((field) => (
                  <option
                    key={`${table.table_name}.${field.field_name}`}
                    value={`${table.table_name}.${field.field_name}`}
                  >
                    {field.display_name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>

          <button
            onClick={handleAddGrouping}
            disabled={!selectedGroupField || isLoading}
            className={clsx(
              'btn w-full',
              selectedGroupField
                ? 'btn-primary'
                : 'btn-secondary opacity-50 cursor-not-allowed'
            )}
            data-testid="add-grouping-btn"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Grouping
          </button>
        </div>
      </div>

      {/* Sorting Section */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <SortAsc className="w-5 h-5 text-hpe-blue" aria-hidden="true" />
          <h3 className="font-medium text-slate-200">Sort Order</h3>
        </div>

        <p className="text-sm text-slate-400 mb-4">
          Define how results should be ordered. Sort by any field in ascending or descending order.
        </p>

        {/* Current sorting rules */}
        {sorting.length > 0 && (
          <div className="mb-4 space-y-2" data-testid="current-sorting">
            {sorting.map((sort, index) => (
              <div
                key={index}
                className="flex items-center justify-between bg-slate-700/50 rounded-lg px-3 py-2 group hover:bg-slate-700 transition-colors"
                data-testid={`sorting-item-${index}`}
              >
                <div className="flex items-center gap-2">
                  {sort.direction === 'ASC' ? (
                    <ArrowUp className="w-4 h-4 text-hpe-blue" aria-hidden="true" />
                  ) : (
                    <ArrowDown className="w-4 h-4 text-hpe-blue" aria-hidden="true" />
                  )}
                  <span className="text-sm text-slate-200">
                    {sort.table && (
                      <span className="text-slate-400">{sort.table}.</span>
                    )}
                    {getFieldDisplayName(sort.table, sort.field)}
                  </span>
                  <button
                    onClick={() => toggleSortDirection(index)}
                    className="text-xs px-2 py-0.5 rounded bg-slate-600 hover:bg-slate-500 text-slate-300 transition-colors"
                    aria-label={`Toggle sort direction for ${sort.field}`}
                    data-testid={`toggle-direction-${index}`}
                  >
                    {sort.direction}
                  </button>
                </div>
                <button
                  onClick={() => onRemoveSorting(index)}
                  className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-rose-400"
                  aria-label={`Remove sorting ${sort.field}`}
                  data-testid={`remove-sorting-${index}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Add sorting rule */}
        <div className="space-y-3">
          <label htmlFor="sort-field-select" className="sr-only">
            Select field to sort by
          </label>
          <select
            id="sort-field-select"
            value={selectedSortField}
            onChange={(e) => setSelectedSortField(e.target.value)}
            className="input w-full"
            disabled={isLoading}
            data-testid="sort-field-select"
          >
            <option value="">Select a field to sort by...</option>
            {tables.map((table) => (
              <optgroup key={table.table_name} label={table.display_name}>
                {table.fields.map((field) => (
                  <option
                    key={`${table.table_name}.${field.field_name}`}
                    value={`${table.table_name}.${field.field_name}`}
                  >
                    {field.display_name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>

          <label htmlFor="sort-direction-select" className="sr-only">
            Select sort direction
          </label>
          <select
            id="sort-direction-select"
            value={selectedSortDirection}
            onChange={(e) => setSelectedSortDirection(e.target.value as SortDirection)}
            className="input w-full"
            disabled={isLoading}
            data-testid="sort-direction-select"
          >
            <option value="ASC">Ascending (A → Z, 0 → 9)</option>
            <option value="DESC">Descending (Z → A, 9 → 0)</option>
          </select>

          <button
            onClick={handleAddSorting}
            disabled={!selectedSortField || isLoading}
            className={clsx(
              'btn w-full',
              selectedSortField
                ? 'btn-primary'
                : 'btn-secondary opacity-50 cursor-not-allowed'
            )}
            data-testid="add-sorting-btn"
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Sorting
          </button>
        </div>
      </div>
    </div>
  )
}
