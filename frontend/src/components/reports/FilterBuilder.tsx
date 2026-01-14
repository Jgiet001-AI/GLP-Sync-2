import {
  Plus,
  X,
  Filter,
  ChevronDown,
  Settings2,
} from 'lucide-react'
import { useMemo } from 'react'
import type {
  FilterConfig,
  FilterOperator,
  LogicOperator,
  FieldMetadata,
  TableMetadata,
  FieldType,
} from '../../types'

interface FilterBuilderProps {
  filters: FilterConfig[]
  tables: TableMetadata[]
  onAddFilter: (filter: FilterConfig) => void
  onRemoveFilter: (index: number) => void
  onUpdateFilter: (index: number, updates: Partial<FilterConfig>) => void
  className?: string
}

// Operator labels for display
const operatorLabels: Record<FilterOperator, string> = {
  equals: 'equals',
  not_equals: 'does not equal',
  contains: 'contains',
  not_contains: 'does not contain',
  starts_with: 'starts with',
  ends_with: 'ends with',
  gt: 'greater than',
  gte: 'greater than or equal',
  lt: 'less than',
  lte: 'less than or equal',
  between: 'between',
  in: 'in list',
  not_in: 'not in list',
  is_null: 'is null',
  is_not_null: 'is not null',
}

// Get operators for a field type
function getOperatorsForFieldType(fieldType: FieldType): FilterOperator[] {
  switch (fieldType) {
    case 'string':
      return [
        'equals',
        'not_equals',
        'contains',
        'not_contains',
        'starts_with',
        'ends_with',
        'in',
        'not_in',
        'is_null',
        'is_not_null',
      ]
    case 'integer':
    case 'float':
      return [
        'equals',
        'not_equals',
        'gt',
        'gte',
        'lt',
        'lte',
        'between',
        'in',
        'not_in',
        'is_null',
        'is_not_null',
      ]
    case 'boolean':
      return ['equals', 'not_equals', 'is_null', 'is_not_null']
    case 'date':
    case 'datetime':
      return [
        'equals',
        'not_equals',
        'gt',
        'gte',
        'lt',
        'lte',
        'between',
        'is_null',
        'is_not_null',
      ]
    case 'uuid':
      return ['equals', 'not_equals', 'in', 'not_in', 'is_null', 'is_not_null']
    case 'jsonb':
      return ['is_null', 'is_not_null']
    default:
      return ['equals', 'not_equals', 'is_null', 'is_not_null']
  }
}

// Check if operator needs a value input
function operatorNeedsValue(operator: FilterOperator): boolean {
  return !['is_null', 'is_not_null'].includes(operator)
}

interface FilterRowProps {
  filter: FilterConfig
  index: number
  tables: TableMetadata[]
  onUpdate: (index: number, updates: Partial<FilterConfig>) => void
  onRemove: (index: number) => void
  showLogic: boolean
}

function FilterRow({
  filter,
  index,
  tables,
  onUpdate,
  onRemove,
  showLogic,
}: FilterRowProps) {
  // Get all available fields from all tables
  const allFields = useMemo(() => {
    const fields: (FieldMetadata & { tableName: string })[] = []
    tables.forEach((table) => {
      table.fields.forEach((field) => {
        if (field.is_filterable) {
          fields.push({ ...field, tableName: table.table_name })
        }
      })
    })
    return fields
  }, [tables])

  // Find the current field metadata
  const currentField = useMemo(() => {
    return allFields.find(
      (f) =>
        f.field_name === filter.field &&
        (filter.table === null || f.tableName === filter.table)
    )
  }, [allFields, filter.field, filter.table])

  // Get available operators for the current field type
  const availableOperators = useMemo(() => {
    if (!currentField) return []
    return getOperatorsForFieldType(currentField.data_type)
  }, [currentField])

  const handleFieldChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const [tableName, fieldName] = e.target.value.split('.')
    const selectedField = allFields.find(
      (f) => f.tableName === tableName && f.field_name === fieldName
    )
    if (selectedField) {
      // Reset operator and value when field changes
      const newOperators = getOperatorsForFieldType(selectedField.data_type)
      onUpdate(index, {
        table: tableName,
        field: fieldName,
        operator: newOperators[0] || 'equals',
        value: null,
      })
    }
  }

  const handleOperatorChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newOperator = e.target.value as FilterOperator
    onUpdate(index, {
      operator: newOperator,
      value: operatorNeedsValue(newOperator) ? filter.value : null,
    })
  }

  const handleValueChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    let value: any = e.target.value

    // Type conversion based on field type
    if (currentField) {
      if (currentField.data_type === 'integer') {
        value = value === '' ? null : parseInt(value, 10)
      } else if (currentField.data_type === 'float') {
        value = value === '' ? null : parseFloat(value)
      } else if (currentField.data_type === 'boolean') {
        value = value === 'true'
      }
    }

    onUpdate(index, { value })
  }

  const handleLogicChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    onUpdate(index, { logic: e.target.value as LogicOperator })
  }

  const renderValueInput = () => {
    if (!operatorNeedsValue(filter.operator)) {
      return null
    }

    // Handle 'in' and 'not_in' operators with comma-separated values
    if (filter.operator === 'in' || filter.operator === 'not_in') {
      return (
        <input
          type="text"
          placeholder="value1, value2, value3"
          value={Array.isArray(filter.value) ? filter.value.join(', ') : filter.value || ''}
          onChange={(e) => {
            const values = e.target.value
              .split(',')
              .map((v) => v.trim())
              .filter((v) => v !== '')
            onUpdate(index, { value: values })
          }}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-violet-500 focus:outline-none"
        />
      )
    }

    // Handle 'between' operator with two values
    if (filter.operator === 'between') {
      const values = Array.isArray(filter.value) ? filter.value : [null, null]
      return (
        <div className="flex flex-1 items-center gap-2">
          <input
            type={
              currentField?.data_type === 'date'
                ? 'date'
                : currentField?.data_type === 'datetime'
                  ? 'datetime-local'
                  : currentField?.data_type === 'integer' || currentField?.data_type === 'float'
                    ? 'number'
                    : 'text'
            }
            placeholder="From"
            value={values[0] || ''}
            onChange={(e) => {
              const newValues = [e.target.value, values[1]]
              onUpdate(index, { value: newValues })
            }}
            className="flex-1 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-violet-500 focus:outline-none"
          />
          <span className="text-slate-500">and</span>
          <input
            type={
              currentField?.data_type === 'date'
                ? 'date'
                : currentField?.data_type === 'datetime'
                  ? 'datetime-local'
                  : currentField?.data_type === 'integer' || currentField?.data_type === 'float'
                    ? 'number'
                    : 'text'
            }
            placeholder="To"
            value={values[1] || ''}
            onChange={(e) => {
              const newValues = [values[0], e.target.value]
              onUpdate(index, { value: newValues })
            }}
            className="flex-1 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-violet-500 focus:outline-none"
          />
        </div>
      )
    }

    // Handle boolean type
    if (currentField?.data_type === 'boolean') {
      return (
        <select
          value={filter.value === null ? '' : String(filter.value)}
          onChange={(e) => onUpdate(index, { value: e.target.value === 'true' })}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none"
        >
          <option value="">Select value...</option>
          <option value="true">True</option>
          <option value="false">False</option>
        </select>
      )
    }

    // Default text/number/date input
    return (
      <input
        type={
          currentField?.data_type === 'date'
            ? 'date'
            : currentField?.data_type === 'datetime'
              ? 'datetime-local'
              : currentField?.data_type === 'integer' || currentField?.data_type === 'float'
                ? 'number'
                : 'text'
        }
        placeholder="Enter value..."
        value={filter.value || ''}
        onChange={handleValueChange}
        className="flex-1 rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-violet-500 focus:outline-none"
      />
    )
  }

  return (
    <div className="group flex items-start gap-2 rounded-lg border border-slate-700/50 bg-slate-800/30 p-3 transition-colors hover:border-slate-600">
      <div className="flex flex-1 flex-col gap-2">
        {/* Logic operator (shown for all filters except the first) */}
        {showLogic && (
          <div className="flex items-center gap-2">
            <select
              value={filter.logic}
              onChange={handleLogicChange}
              className="w-20 rounded-md border border-slate-700 bg-slate-800/50 px-2 py-1 text-xs font-medium text-white focus:border-violet-500 focus:outline-none"
            >
              <option value="AND">AND</option>
              <option value="OR">OR</option>
            </select>
            <div className="h-px flex-1 bg-slate-700/50" />
          </div>
        )}

        {/* Filter configuration row */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Field selector */}
          <select
            value={filter.table && filter.field ? `${filter.table}.${filter.field}` : ''}
            onChange={handleFieldChange}
            className="min-w-[180px] rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none"
          >
            <option value="">Select field...</option>
            {tables.map((table) => (
              <optgroup key={table.table_name} label={table.display_name}>
                {table.fields
                  .filter((f) => f.is_filterable)
                  .map((field) => (
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

          {/* Operator selector */}
          <select
            value={filter.operator}
            onChange={handleOperatorChange}
            disabled={!currentField}
            className="min-w-[140px] rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2 text-sm text-white focus:border-violet-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {availableOperators.map((op) => (
              <option key={op} value={op}>
                {operatorLabels[op]}
              </option>
            ))}
          </select>

          {/* Value input */}
          {renderValueInput()}
        </div>
      </div>

      {/* Remove button */}
      <button
        type="button"
        onClick={() => onRemove(index)}
        className="flex-shrink-0 rounded-md p-1.5 text-slate-500 opacity-0 transition-all hover:bg-rose-500/10 hover:text-rose-400 group-hover:opacity-100"
        title="Remove filter"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

export function FilterBuilder({
  filters,
  tables,
  onAddFilter,
  onRemoveFilter,
  onUpdateFilter,
  className = '',
}: FilterBuilderProps) {
  const handleAddFilter = () => {
    // Find the first filterable field
    const firstTable = tables[0]
    const firstField = firstTable?.fields.find((f) => f.is_filterable)

    if (firstTable && firstField) {
      const operators = getOperatorsForFieldType(firstField.data_type)
      const newFilter: FilterConfig = {
        table: firstTable.table_name,
        field: firstField.field_name,
        operator: operators[0] || 'equals',
        value: null,
        logic: 'AND',
      }
      onAddFilter(newFilter)
    }
  }

  return (
    <div className={`flex flex-col ${className}`}>
      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-violet-400" />
          <h3 className="text-sm font-medium text-slate-200">Filters</h3>
          {filters.length > 0 && (
            <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-xs text-violet-400">
              {filters.length}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleAddFilter}
          className="flex items-center gap-1.5 rounded-lg bg-violet-500/10 px-3 py-1.5 text-xs font-medium text-violet-400 transition-colors hover:bg-violet-500/20"
        >
          <Plus className="h-3.5 w-3.5" />
          Add Filter
        </button>
      </div>

      {/* Filter list */}
      <div className="space-y-2">
        {filters.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-700/50 bg-slate-800/20 p-8 text-center">
            <Settings2 className="mx-auto h-8 w-8 text-slate-600" />
            <p className="mt-2 text-sm text-slate-500">No filters yet</p>
            <p className="mt-1 text-xs text-slate-600">
              Add filters to refine your report results
            </p>
          </div>
        ) : (
          filters.map((filter, index) => (
            <FilterRow
              key={index}
              filter={filter}
              index={index}
              tables={tables}
              onUpdate={onUpdateFilter}
              onRemove={onRemoveFilter}
              showLogic={index > 0}
            />
          ))
        )}
      </div>

      {/* Filter logic explanation */}
      {filters.length > 1 && (
        <div className="mt-3 rounded-lg border border-slate-700/30 bg-slate-800/20 p-2.5 text-xs text-slate-500">
          <div className="flex items-start gap-2">
            <ChevronDown className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
            <div>
              Filters are combined using the logic operators (AND/OR) shown above each filter.
              <span className="ml-1 font-medium text-slate-400">AND</span> requires all conditions to match,
              <span className="ml-1 font-medium text-slate-400">OR</span> requires at least one condition to match.
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
