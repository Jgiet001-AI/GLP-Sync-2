import { useState, useEffect } from 'react'
import { Save, Play, Trash2, RotateCcw, FileText } from 'lucide-react'
import clsx from 'clsx'
import { useReportBuilder } from '../../hooks/useReportBuilder'
import { FieldSelector } from './FieldSelector'
import { FilterBuilder } from './FilterBuilder'
import { GroupingPanel } from './GroupingPanel'
import { ReportPreview } from './ReportPreview'
import type { FieldMetadata } from '../../types'

interface ReportBuilderPanelProps {
  className?: string
}

export function ReportBuilderPanel({ className = '' }: ReportBuilderPanelProps) {
  const {
    // State
    fields,
    filters,
    grouping,
    sorting,
    currentReport,
    previewData,

    // Queries
    availableFields,
    isLoadingFields,

    // Field actions
    addField,
    removeField,

    // Filter actions
    addFilter,
    removeFilter,
    updateFilter,

    // Grouping actions
    addGrouping,
    removeGrouping,

    // Sorting actions
    addSorting,
    removeSorting,
    updateSorting,

    // Report management
    saveReport,
    deleteReport,
    executeReport,
    downloadReport,
    resetConfig,

    // Mutation states
    isSaving,
    isDeleting,
    isExecuting,
  } = useReportBuilder()

  const [reportName, setReportName] = useState(currentReport?.name || '')
  const [reportDescription, setReportDescription] = useState(currentReport?.description || '')
  const [showSaveDialog, setShowSaveDialog] = useState(false)

  // Reset form when currentReport changes (e.g., "+ New" button clicked)
  useEffect(() => {
    setReportName(currentReport?.name || '')
    setReportDescription(currentReport?.description || '')
  }, [currentReport])

  // Convert fields to "table.field" format for FieldSelector
  const selectedFieldKeys = fields.map((f) => `${f.table}.${f.field}`)

  // Handle field selection from FieldSelector
  const handleFieldSelect = (field: FieldMetadata) => {
    const fieldKey = `${field.table}.${field.field_name}`
    if (selectedFieldKeys.includes(fieldKey)) {
      // Remove field if already selected
      const index = fields.findIndex((f) => f.table === field.table && f.field === field.field_name)
      if (index !== -1) {
        removeField(index)
      }
    } else {
      // Add field if not selected
      addField(field.table, field.field_name)
    }
  }

  // Handle field drop from drag-and-drop
  const handleFieldDrop = (e: React.DragEvent) => {
    e.preventDefault()
    try {
      const data = JSON.parse(e.dataTransfer.getData('application/json'))
      if (data.table && data.field) {
        addField(data.table, data.field)
      }
    } catch (error) {
      console.error('Failed to parse dropped field data:', error)
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }

  const handleSaveClick = () => {
    if (currentReport) {
      // Update existing report
      saveReport(reportName, reportDescription)
    } else {
      // Show dialog for new report
      setShowSaveDialog(true)
    }
  }

  const handleSaveConfirm = () => {
    if (reportName.trim()) {
      saveReport(reportName, reportDescription || null)
      setShowSaveDialog(false)
    }
  }

  const handleDeleteClick = () => {
    if (currentReport && window.confirm(`Delete report "${currentReport.name}"?`)) {
      deleteReport(currentReport.id)
      setReportName('')
      setReportDescription('')
    }
  }

  const handleRunReport = () => {
    executeReport()
  }

  const handleDownload = (format: 'csv' | 'xlsx') => {
    downloadReport(format)
  }

  const handleReset = () => {
    if (window.confirm('Clear all report configuration?')) {
      resetConfig()
      setReportName('')
      setReportDescription('')
    }
  }

  // No adapter needed - GroupingPanel now uses correct TableMetadata properties
  const availableTables = availableFields?.tables || []

  if (isLoadingFields) {
    return (
      <div className={`space-y-6 ${className}`} data-testid="report-builder-panel-loading">
        <div className="card">
          <div className="animate-pulse">
            <div className="h-8 bg-slate-700 rounded w-1/3 mb-6" />
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="h-96 bg-slate-700 rounded" />
              <div className="h-96 bg-slate-700 rounded" />
              <div className="h-96 bg-slate-700 rounded" />
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`space-y-6 ${className}`} data-testid="report-builder-panel">
      {/* Header with report name and actions */}
      <div className="card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <FileText className="h-5 w-5 text-hpe-purple" aria-hidden="true" />
              <input
                type="text"
                placeholder="Untitled Report"
                value={reportName}
                onChange={(e) => setReportName(e.target.value)}
                className="input text-lg font-medium border-0 bg-transparent px-0 focus:ring-0"
                data-testid="report-name-input"
              />
            </div>
            {currentReport && (
              <p className="text-sm text-slate-400 mt-1 ml-8">
                Last updated: {new Date(currentReport.updated_at).toLocaleString()}
              </p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="btn btn-secondary btn-sm flex items-center gap-2"
              disabled={fields.length === 0 && filters.length === 0}
              data-testid="reset-btn"
            >
              <RotateCcw className="h-4 w-4" />
              Clear
            </button>

            {currentReport && (
              <button
                onClick={handleDeleteClick}
                disabled={isDeleting}
                className="btn btn-secondary btn-sm flex items-center gap-2 text-rose-400 hover:text-rose-300"
                data-testid="delete-btn"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            )}

            <button
              onClick={handleSaveClick}
              disabled={isSaving || fields.length === 0}
              className={clsx(
                'btn btn-sm flex items-center gap-2',
                fields.length > 0 ? 'btn-primary' : 'btn-secondary opacity-50 cursor-not-allowed'
              )}
              data-testid="save-btn"
            >
              <Save className="h-4 w-4" />
              {currentReport ? 'Update' : 'Save'}
            </button>

            <button
              onClick={handleRunReport}
              disabled={isExecuting || !currentReport}
              className={clsx(
                'btn btn-sm flex items-center gap-2',
                currentReport ? 'btn-primary' : 'btn-secondary opacity-50 cursor-not-allowed'
              )}
              data-testid="run-report-btn"
            >
              <Play className="h-4 w-4" />
              Run Report
            </button>
          </div>
        </div>
      </div>

      {/* Main 3-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left column: Field Selector */}
        <div className="lg:col-span-3">
          <FieldSelector
            tables={availableFields?.tables || []}
            selectedFields={selectedFieldKeys}
            onFieldSelect={handleFieldSelect}
            data-testid="field-selector"
          />
        </div>

        {/* Middle column: Selected Fields, Filters, and Grouping */}
        <div className="lg:col-span-4 space-y-6">
          {/* Selected Fields Drop Zone */}
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-slate-200">Selected Fields</h3>
              {fields.length > 0 && (
                <span className="rounded-full bg-violet-500/20 px-2 py-0.5 text-xs text-violet-400">
                  {fields.length}
                </span>
              )}
            </div>

            <div
              onDrop={handleFieldDrop}
              onDragOver={handleDragOver}
              className={clsx(
                'min-h-[100px] rounded-lg border-2 border-dashed transition-colors',
                fields.length === 0
                  ? 'border-slate-700 bg-slate-800/20'
                  : 'border-slate-700/50 bg-slate-800/10'
              )}
              data-testid="selected-fields-dropzone"
            >
              {fields.length === 0 ? (
                <div className="flex items-center justify-center py-8 text-center">
                  <div>
                    <p className="text-sm text-slate-500">Drop fields here</p>
                    <p className="text-xs text-slate-600 mt-1">or click fields to select</p>
                  </div>
                </div>
              ) : (
                <div className="p-3 space-y-2">
                  {fields.map((field, index) => (
                    <div
                      key={index}
                      className="flex items-center justify-between bg-slate-700/50 rounded-lg px-3 py-2 group hover:bg-slate-700 transition-colors"
                      data-testid={`selected-field-${index}`}
                    >
                      <div className="flex items-center gap-2 flex-1 min-w-0">
                        <span className="text-sm text-slate-300 truncate">
                          {field.table && (
                            <span className="text-slate-500">{field.table}.</span>
                          )}
                          {field.field}
                        </span>
                        {field.aggregation && (
                          <span className="rounded bg-violet-500/20 px-2 py-0.5 text-xs text-violet-400">
                            {field.aggregation}
                          </span>
                        )}
                      </div>
                      <button
                        onClick={() => removeField(index)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-rose-400"
                        aria-label={`Remove field ${field.field}`}
                        data-testid={`remove-field-${index}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Filters */}
          <FilterBuilder
            filters={filters}
            tables={availableFields?.tables || []}
            onAddFilter={addFilter}
            onRemoveFilter={removeFilter}
            onUpdateFilter={updateFilter}
            data-testid="filter-builder"
          />

          {/* Grouping and Sorting */}
          <GroupingPanel
            tables={availableTables}
            grouping={grouping}
            sorting={sorting}
            onAddGrouping={addGrouping}
            onRemoveGrouping={removeGrouping}
            onAddSorting={addSorting}
            onRemoveSorting={removeSorting}
            onUpdateSorting={updateSorting}
            isLoading={false}
            data-testid="grouping-panel"
          />
        </div>

        {/* Right column: Preview */}
        <div className="lg:col-span-5">
          <ReportPreview
            data={previewData}
            isLoading={isExecuting}
            onDownload={handleDownload}
            data-testid="report-preview"
          />
        </div>
      </div>

      {/* Save Dialog */}
      {showSaveDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" data-testid="save-dialog">
          <div className="card max-w-md w-full mx-4">
            <h3 className="text-lg font-medium text-slate-200 mb-4">Save Report</h3>

            <div className="space-y-4">
              <div>
                <label htmlFor="save-name" className="block text-sm font-medium text-slate-300 mb-2">
                  Report Name *
                </label>
                <input
                  id="save-name"
                  type="text"
                  placeholder="My Custom Report"
                  value={reportName}
                  onChange={(e) => setReportName(e.target.value)}
                  className="input w-full"
                  autoFocus
                  data-testid="save-name-input"
                />
              </div>

              <div>
                <label htmlFor="save-description" className="block text-sm font-medium text-slate-300 mb-2">
                  Description
                </label>
                <textarea
                  id="save-description"
                  placeholder="Optional description..."
                  value={reportDescription}
                  onChange={(e) => setReportDescription(e.target.value)}
                  className="input w-full min-h-[80px] resize-none"
                  data-testid="save-description-input"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  onClick={() => setShowSaveDialog(false)}
                  className="btn btn-secondary flex-1"
                  data-testid="save-cancel-btn"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveConfirm}
                  disabled={!reportName.trim() || isSaving}
                  className={clsx(
                    'btn flex-1',
                    reportName.trim() ? 'btn-primary' : 'btn-secondary opacity-50 cursor-not-allowed'
                  )}
                  data-testid="save-confirm-btn"
                >
                  Save Report
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
