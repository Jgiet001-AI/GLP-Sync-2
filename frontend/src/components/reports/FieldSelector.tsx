import {
  ChevronDown,
  ChevronUp,
  Search,
  Type,
  Hash,
  Calendar,
  Clock,
  ToggleLeft,
  Fingerprint,
  Braces,
  GripVertical,
} from 'lucide-react'
import { useState, useMemo } from 'react'
import type { TableMetadata, FieldMetadata, FieldType } from '../../types'

interface FieldSelectorProps {
  tables: TableMetadata[]
  selectedFields: string[] // Array of "table.field" strings
  onFieldSelect?: (field: FieldMetadata) => void
  className?: string
}

// Icon mapping for field types
const fieldTypeIcons: Record<FieldType, React.ReactNode> = {
  string: <Type className="h-3.5 w-3.5" />,
  integer: <Hash className="h-3.5 w-3.5" />,
  float: <Hash className="h-3.5 w-3.5" />,
  boolean: <ToggleLeft className="h-3.5 w-3.5" />,
  date: <Calendar className="h-3.5 w-3.5" />,
  datetime: <Clock className="h-3.5 w-3.5" />,
  uuid: <Fingerprint className="h-3.5 w-3.5" />,
  jsonb: <Braces className="h-3.5 w-3.5" />,
}

interface TableSectionProps {
  table: TableMetadata
  selectedFields: string[]
  onFieldSelect?: (field: FieldMetadata) => void
  defaultOpen?: boolean
}

function TableSection({
  table,
  selectedFields,
  onFieldSelect,
  defaultOpen = false,
}: TableSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)
  const [searchTerm, setSearchTerm] = useState('')
  const [draggedField, setDraggedField] = useState<string | null>(null)

  const filteredFields = useMemo(() => {
    if (!searchTerm) return table.fields
    const lower = searchTerm.toLowerCase()
    return table.fields.filter(
      (field) =>
        field.display_name.toLowerCase().includes(lower) ||
        field.field_name.toLowerCase().includes(lower) ||
        field.description?.toLowerCase().includes(lower)
    )
  }, [table.fields, searchTerm])

  const selectedCount = useMemo(() => {
    return table.fields.filter((field) =>
      selectedFields.includes(`${table.table_name}.${field.field_name}`)
    ).length
  }, [table.fields, table.table_name, selectedFields])

  const handleDragStart = (field: FieldMetadata, e: React.DragEvent) => {
    setDraggedField(`${table.table_name}.${field.field_name}`)
    // Set drag data with field information
    e.dataTransfer.effectAllowed = 'copy'
    e.dataTransfer.setData(
      'application/json',
      JSON.stringify({
        table: table.table_name,
        field: field.field_name,
        display_name: field.display_name,
        data_type: field.data_type,
      })
    )
  }

  const handleDragEnd = () => {
    setDraggedField(null)
  }

  const handleClick = (field: FieldMetadata) => {
    if (onFieldSelect) {
      onFieldSelect(field)
    }
  }

  return (
    <div className="border-b border-slate-700/50 last:border-b-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between px-4 py-2.5 text-sm font-medium text-slate-300 hover:bg-slate-700/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span>{table.display_name}</span>
          {selectedCount > 0 && (
            <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-xs text-violet-400">
              {selectedCount}
            </span>
          )}
        </div>
        {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>

      {isOpen && (
        <div className="px-4 pb-3">
          {table.fields.length > 8 && (
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
              <input
                type="text"
                placeholder="Search fields..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800/50 py-1.5 pl-8 pr-3 text-xs text-white placeholder-slate-500 focus:border-violet-500 focus:outline-none"
              />
            </div>
          )}
          <div className="space-y-0.5 overflow-y-auto max-h-96">
            {filteredFields.length === 0 ? (
              <p className="py-2 text-xs text-slate-500 text-center">No fields found</p>
            ) : (
              filteredFields.map((field) => {
                const fieldKey = `${table.table_name}.${field.field_name}`
                const isSelected = selectedFields.includes(fieldKey)
                const isDragging = draggedField === fieldKey

                return (
                  <div
                    key={fieldKey}
                    draggable
                    onDragStart={(e) => handleDragStart(field, e)}
                    onDragEnd={handleDragEnd}
                    onClick={() => handleClick(field)}
                    className={`group flex items-center gap-2 rounded-md px-2 py-2 text-xs transition-all cursor-grab active:cursor-grabbing ${
                      isDragging
                        ? 'opacity-50 scale-95'
                        : isSelected
                        ? 'bg-violet-500/20 text-violet-300 hover:bg-violet-500/30'
                        : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-200'
                    }`}
                    title={field.description || field.display_name}
                  >
                    <GripVertical className="h-3.5 w-3.5 flex-shrink-0 text-slate-600 group-hover:text-slate-400" />
                    <div className="flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center text-slate-500">
                      {fieldTypeIcons[field.data_type]}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{field.display_name}</div>
                      {field.description && (
                        <div className="text-[10px] text-slate-500 truncate mt-0.5">
                          {field.description}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function FieldSelector({
  tables,
  selectedFields,
  onFieldSelect,
  className = '',
}: FieldSelectorProps) {
  return (
    <div
      className={`flex flex-col rounded-lg border border-slate-700 bg-slate-800/50 ${className}`}
    >
      <div className="border-b border-slate-700/50 px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-200">Available Fields</h3>
        <p className="mt-1 text-xs text-slate-500">
          Drag fields to add them to your report
        </p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {tables.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-sm text-slate-500">
            No tables available
          </div>
        ) : (
          tables.map((table, index) => (
            <TableSection
              key={table.table_name}
              table={table}
              selectedFields={selectedFields}
              onFieldSelect={onFieldSelect}
              defaultOpen={index === 0}
            />
          ))
        )}
      </div>
    </div>
  )
}
