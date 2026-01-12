import { memo, useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { ArrowLeft, ArrowRight, Play, CheckCircle, ChevronDown, Filter } from 'lucide-react'
import {
  AddDevicesPanel,
  DeviceTable,
  FileUpload,
  PerTypeAssignmentPanel,
  ProgressModal,
  ReportViewer,
  WorkflowSteps,
} from '../components'
import { useAssignment } from '../hooks/useAssignment'
import { usePerTypeAssignment } from '../hooks/usePerTypeAssignment'
import { useAssignmentProgress } from '../hooks/useAssignmentProgress'
import type { DeviceAssignment as DeviceAssignmentType, ApplyRequest } from '../types'

export function DeviceAssignment() {
  const {
    step,
    devices,
    selectedSerials,
    options,
    applyResult,
    report,
    isUploading,
    isLoadingOptions,
    isApplying,
    isSyncing,
    uploadFile,
    toggleDevice,
    selectAll,
    deselectAll,
    deselectComplete,
    selectComplete,
    selectByType,
    deselectByType,
    selectByModel,
    deselectByModel,
    selectNotInDb,
    deselectNotInDb,
    applyAssignments,
    syncWithGreenLake,
    reset,
    goToStep,
    selectedCount,
    totalCount,
    setDevices,
  } = useAssignment()

  // Per-type assignment hook
  const {
    deviceGroups,
    typeConfigs,
    globalApplicationId,
    setGlobalApplicationId,
    updateTypeConfig,
    applyAllAssignments,
  } = usePerTypeAssignment(devices, selectedSerials, options, setDevices)

  // SSE streaming progress hook
  const { progress: sseProgress, error: sseError, startStream, stop: stopStream } = useAssignmentProgress()

  // Progress modal state
  const [showProgress, setShowProgress] = useState(false)
  const [progressComplete, setProgressComplete] = useState(false)
  const [progressError, setProgressError] = useState(false)
  const [progressErrorMessage, setProgressErrorMessage] = useState<string | undefined>()

  // Track whether we're using SSE or fallback
  const useSSE = useRef(true)

  // Progress phases for the modal
  const batchCount = Math.ceil(selectedCount / 25)
  const newDeviceCount = devices.filter(d => !d.device_id && selectedSerials.has(d.serial_number)).length

  const progressPhases = useMemo(() => [
    {
      id: 'prepare',
      name: 'Preparing',
      description: 'Validating devices and configurations',
      estimatedSeconds: 2,
    },
    {
      id: 'applications',
      name: 'Assigning Regions',
      description: 'Setting application/region for devices (rate-limited)',
      estimatedSeconds: batchCount * 5,
    },
    {
      id: 'subscriptions',
      name: 'Assigning Subscriptions',
      description: `Assigning licenses to ${selectedCount} devices (${batchCount} batches, rate-limited)`,
      estimatedSeconds: batchCount * 5,
    },
    {
      id: 'tags',
      name: 'Updating Tags',
      description: 'Applying tags to devices (rate-limited)',
      estimatedSeconds: batchCount * 5,
    },
    {
      id: 'new_devices',
      name: 'Adding New Devices',
      description: `Registering ${newDeviceCount} new devices (rate-limited)`,
      estimatedSeconds: newDeviceCount * 4,
    },
    {
      id: 'complete',
      name: 'Finalizing',
      description: 'Completing the assignment process',
      estimatedSeconds: 2,
    },
  ], [selectedCount, batchCount, newDeviceCount])

  // Get current phase index from SSE progress
  const currentPhaseIndex = useMemo(() => {
    if (!sseProgress?.phase) return 0
    const phaseMap: Record<string, number> = {
      'applications': 1,
      'subscriptions': 2,
      'tags': 3,
      'new_devices': 4,
    }
    return phaseMap[sseProgress.phase] ?? 0
  }, [sseProgress?.phase])

  // Convert SSE progress to batch progress format
  const batchProgress = useMemo(() => {
    if (!sseProgress?.batch) return undefined
    return {
      currentBatch: sseProgress.batch.currentBatch,
      totalBatches: sseProgress.batch.totalBatches,
      devicesInBatch: sseProgress.batch.devicesInBatch,
    }
  }, [sseProgress?.batch])

  // Convert SSE timing to timing format
  const timing = useMemo(() => {
    if (!sseProgress?.timing) return undefined
    return {
      elapsedSeconds: sseProgress.timing.elapsedSeconds,
      estimatedRemainingSeconds: sseProgress.timing.estimatedRemainingSeconds,
      avgBatchSeconds: sseProgress.timing.avgBatchSeconds,
    }
  }, [sseProgress?.timing])

  // Convert SSE stats
  const stats = useMemo(() => {
    if (!sseProgress?.stats) return undefined
    return {
      successCount: sseProgress.stats.successCount,
      errorCount: sseProgress.stats.errorCount,
      totalDevices: sseProgress.stats.totalDevices,
    }
  }, [sseProgress?.stats])

  // Handle SSE completion/error
  useEffect(() => {
    if (!showProgress || !useSSE.current) return

    if (sseProgress?.type === 'complete') {
      setProgressComplete(true)
    } else if (sseProgress?.type === 'error' || sseError) {
      setProgressError(true)
      setProgressErrorMessage(sseError || sseProgress?.error || 'Assignment failed')
    }
  }, [sseProgress, sseError, showProgress])

  // Fallback: Handle non-SSE apply completion/error
  useEffect(() => {
    if (!showProgress || useSSE.current) return

    if (!isApplying && applyResult) {
      if (applyResult.success) {
        setProgressComplete(true)
      } else {
        setProgressError(true)
        setProgressErrorMessage(`${applyResult.errors} operation(s) failed`)
      }
    }
  }, [isApplying, applyResult, showProgress])

  // Combined handler: apply selections to devices THEN trigger API call via SSE
  const handleApplyAll = useCallback(async () => {
    // Reset progress state
    setShowProgress(true)
    setProgressComplete(false)
    setProgressError(false)
    setProgressErrorMessage(undefined)

    // First, apply the per-type selections to the device objects
    const updatedDevices = applyAllAssignments()

    // Build the request for SSE streaming
    const selectedDevices = updatedDevices.filter(d => selectedSerials.has(d.serial_number))
    const request: ApplyRequest = {
      devices: selectedDevices.map(d => ({
        serial_number: d.serial_number,
        mac_address: d.mac_address,
        device_id: d.device_id,
        device_type: d.device_type,
        current_subscription_id: d.current_subscription_id,
        current_application_id: d.current_application_id,
        current_tags: d.current_tags,
        selected_subscription_id: d.selected_subscription_id,
        selected_application_id: d.selected_application_id,
        selected_region: d.selected_region,
        selected_tags: d.selected_tags,
      })),
      wait_for_completion: true,
    }

    // Try SSE streaming first
    useSSE.current = true
    try {
      await startStream(request)
    } catch {
      // If SSE fails, fall back to regular API
      useSSE.current = false
      applyAssignments(updatedDevices)
    }
  }, [applyAllAssignments, applyAssignments, selectedSerials, startStream])

  // Cancel handler
  const handleCancel = useCallback(() => {
    stopStream()
    setShowProgress(false)
  }, [stopStream])

  // Close progress modal and go to results
  const handleProgressClose = useCallback(() => {
    setShowProgress(false)
    if (progressComplete) {
      goToStep('report')
    }
  }, [progressComplete, goToStep])

  return (
    <div className="min-h-screen bg-slate-900" data-testid="device-assignment-page">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-white">
                Device Assignment
              </h1>
              <p className="text-sm text-slate-400 mt-1">
                Bulk assign subscriptions, applications, and tags to devices
              </p>
            </div>
            {/* HPE Logo - inline SVG for reliability */}
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded bg-hpe-green flex items-center justify-center">
                <span className="text-white font-bold text-sm">HPE</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Workflow Steps */}
      <div className="border-b border-slate-800 py-4 bg-slate-900/50">
        <div className="max-w-7xl mx-auto px-6">
          <WorkflowSteps currentStep={step} onStepClick={goToStep} />
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Upload Step */}
        {step === 'upload' && (
          <div className="flex flex-col items-center justify-center min-h-[400px]" data-testid="upload-step">
            <FileUpload onUpload={uploadFile} isUploading={isUploading} />
          </div>
        )}

        {/* Review Step */}
        {step === 'review' && (
          <div data-testid="review-step">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-semibold text-white">Review Devices</h2>
                <p className="text-slate-400 mt-1">
                  {totalCount} devices loaded, {selectedCount} selected
                </p>
              </div>
              <div className="flex gap-3">
                <button
                  onClick={reset}
                  className="btn btn-secondary"
                  data-testid="review-back-btn"
                >
                  <ArrowLeft className="w-4 h-4 mr-2" aria-hidden="true" />
                  Back
                </button>
                <button
                  onClick={() => goToStep('assign')}
                  disabled={selectedCount === 0}
                  className="btn btn-primary"
                  data-testid="review-continue-btn"
                >
                  Continue
                  <ArrowRight className="w-4 h-4 ml-2" aria-hidden="true" />
                </button>
              </div>
            </div>

            <div className="card">
              <DeviceTable
                devices={devices}
                selectedSerials={selectedSerials}
                onToggle={toggleDevice}
                onSelectAll={selectAll}
                onDeselectAll={deselectAll}
              />
            </div>

            {/* Statistics */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mt-6">
              <StatCard label="Total" value={totalCount} />
              <StatCard label="Found in DB" value={devices.filter((d) => d.device_id).length} />
              <StatCard
                label="Not in DB"
                value={devices.filter((d) => !d.device_id).length}
                variant="warning"
              />
              <StatCard
                label="Fully Assigned"
                value={devices.filter((d) => d.status === 'fully_assigned').length}
                variant="success"
              />
              <StatCard
                label="Need Assignment"
                value={
                  devices.filter(
                    (d) => d.status === 'partial' || d.status === 'unassigned'
                  ).length
                }
                variant="info"
              />
            </div>

            {/* Deselect Complete Button */}
            {devices.filter((d) => d.status === 'fully_assigned').length > 0 && (
              <div className="mt-4 flex justify-end">
                <button
                  onClick={deselectComplete}
                  className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20"
                  data-testid="deselect-complete-btn"
                >
                  <CheckCircle className="h-4 w-4" />
                  Deselect Complete ({devices.filter((d) => d.status === 'fully_assigned' && selectedSerials.has(d.serial_number)).length})
                </button>
              </div>
            )}
          </div>
        )}

        {/* Assign Step */}
        {step === 'assign' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6" data-testid="assign-step">
            {/* Device Table */}
            <div className="lg:col-span-2">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-4">
                  <h2 className="text-xl font-semibold text-white">Select & Assign</h2>
                  {/* Selection Dropdown */}
                  <SelectionDropdown
                    devices={devices}
                    selectedSerials={selectedSerials}
                    onSelectAll={selectAll}
                    onDeselectAll={deselectAll}
                    onSelectComplete={selectComplete}
                    onDeselectComplete={deselectComplete}
                    onSelectByType={selectByType}
                    onDeselectByType={deselectByType}
                    onSelectByModel={selectByModel}
                    onDeselectByModel={deselectByModel}
                    onSelectNotInDb={selectNotInDb}
                    onDeselectNotInDb={deselectNotInDb}
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => goToStep('review')}
                    className="btn btn-secondary"
                    data-testid="assign-back-btn"
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" aria-hidden="true" />
                    Back
                  </button>
                  <button
                    onClick={() => applyAssignments()}
                    disabled={selectedCount === 0 || isApplying}
                    className="btn btn-primary"
                    data-testid="apply-assignments-btn"
                  >
                    {isApplying ? (
                      <>
                        <div
                          className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent mr-2"
                          role="status"
                          aria-label="Applying assignments"
                        />
                        Applying...
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4 mr-2" aria-hidden="true" />
                        Apply Assignments
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Warning for devices not in GreenLake */}
              {devices.filter((d) => !d.device_id && selectedSerials.has(d.serial_number)).length > 0 && (
                <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
                  <div className="flex items-start gap-3">
                    <span className="text-amber-500 text-xl">⚠</span>
                    <div>
                      <p className="font-medium text-amber-400">
                        {devices.filter((d) => !d.device_id && selectedSerials.has(d.serial_number)).length} device(s) not found in GreenLake
                      </p>
                      <p className="text-sm text-amber-400/80 mt-1">
                        These devices must be added to GreenLake before licenses can be assigned.
                        Use the Selection dropdown to deselect them.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div className="card">
                <DeviceTable
                  devices={devices}
                  selectedSerials={selectedSerials}
                  onToggle={toggleDevice}
                  onSelectAll={selectAll}
                  onDeselectAll={deselectAll}
                />
              </div>
            </div>

            {/* Per-Type Assignment Panel */}
            <div>
              <h2 className="text-xl font-semibold text-white mb-4">Assignment Options</h2>
              <PerTypeAssignmentPanel
                deviceGroups={deviceGroups}
                typeConfigs={typeConfigs}
                globalApplicationId={globalApplicationId}
                options={options}
                selectedCount={selectedCount}
                isLoading={isLoadingOptions || isApplying}
                onGlobalApplicationChange={setGlobalApplicationId}
                onTypeConfigChange={updateTypeConfig}
                onApplyAll={handleApplyAll}
              />
            </div>
          </div>
        )}

        {/* Report Step */}
        {step === 'report' && (
          <div className="max-w-3xl mx-auto space-y-6" data-testid="report-step">
            <h2 className="text-xl font-semibold text-white">Assignment Report</h2>
            <ReportViewer
              applyResult={applyResult}
              report={report}
              onSync={syncWithGreenLake}
              onReset={reset}
              isSyncing={isSyncing}
            />

            {/* Add Devices Panel - shown after assignments are complete */}
            <AddDevicesPanel
              devices={devices}
              onDevicesAdded={syncWithGreenLake}
            />
          </div>
        )}
      </main>

      {/* Progress Modal */}
      <ProgressModal
        isOpen={showProgress}
        title="Applying Assignments"
        phases={progressPhases}
        currentPhaseIndex={currentPhaseIndex}
        currentPhaseName={sseProgress?.phase}
        totalDevices={selectedCount}
        isComplete={progressComplete}
        isError={progressError}
        errorMessage={progressErrorMessage}
        onClose={handleProgressClose}
        onCancel={handleCancel}
        batchProgress={batchProgress}
        timing={timing}
        stats={stats}
      />
    </div>
  )
}

// Selection Dropdown Component
interface SelectionDropdownProps {
  devices: DeviceAssignmentType[]
  selectedSerials: Set<string>
  onSelectAll: () => void
  onDeselectAll: () => void
  onSelectComplete: () => void
  onDeselectComplete: () => void
  onSelectByType: (type: string) => void
  onDeselectByType: (type: string) => void
  onSelectByModel: (model: string) => void
  onDeselectByModel: (model: string) => void
  onSelectNotInDb: () => void
  onDeselectNotInDb: () => void
}

function SelectionDropdown({
  devices,
  selectedSerials,
  onSelectAll,
  onDeselectAll,
  onSelectComplete,
  onDeselectComplete,
  onSelectByType,
  onDeselectByType,
  onSelectByModel,
  onDeselectByModel,
  onSelectNotInDb,
  onDeselectNotInDb,
}: SelectionDropdownProps) {
  const [isOpen, setIsOpen] = useState(false)

  // Get unique types and models with counts
  const { types, models, completeCount, selectedCompleteCount, notInDbCount, selectedNotInDbCount } = useMemo(() => {
    const typeMap = new Map<string, { total: number; selected: number }>()
    const modelMap = new Map<string, { total: number; selected: number }>()
    let complete = 0
    let selectedComplete = 0
    let notInDb = 0
    let selectedNotInDb = 0

    devices.forEach((d) => {
      // Count by type
      if (d.device_type) {
        const existing = typeMap.get(d.device_type) || { total: 0, selected: 0 }
        existing.total++
        if (selectedSerials.has(d.serial_number)) existing.selected++
        typeMap.set(d.device_type, existing)
      }

      // Count by model
      if (d.model) {
        const existing = modelMap.get(d.model) || { total: 0, selected: 0 }
        existing.total++
        if (selectedSerials.has(d.serial_number)) existing.selected++
        modelMap.set(d.model, existing)
      }

      // Count complete
      if (d.status === 'fully_assigned') {
        complete++
        if (selectedSerials.has(d.serial_number)) selectedComplete++
      }

      // Count not in DB
      if (!d.device_id) {
        notInDb++
        if (selectedSerials.has(d.serial_number)) selectedNotInDb++
      }
    })

    return {
      types: Array.from(typeMap.entries()).sort((a, b) => b[1].total - a[1].total),
      models: Array.from(modelMap.entries()).sort((a, b) => b[1].total - a[1].total),
      completeCount: complete,
      selectedCompleteCount: selectedComplete,
      notInDbCount: notInDb,
      selectedNotInDbCount: selectedNotInDb,
    }
  }, [devices, selectedSerials])

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 rounded-lg border border-slate-600 bg-slate-800 px-3 py-1.5 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-700 hover:text-white"
      >
        <Filter className="h-4 w-4" />
        Selection
        <ChevronDown className={`h-4 w-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />

          {/* Dropdown Menu */}
          <div className="absolute left-0 top-full z-50 mt-1 w-64 rounded-lg border border-slate-700 bg-slate-800 py-1 shadow-xl">
            {/* All */}
            <div className="px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-slate-500">
              All Devices
            </div>
            <button
              onClick={() => { onSelectAll(); setIsOpen(false) }}
              className="flex w-full items-center justify-between px-3 py-2 text-sm text-slate-300 hover:bg-slate-700"
            >
              <span>Select All</span>
              <span className="text-slate-500">{devices.length}</span>
            </button>
            <button
              onClick={() => { onDeselectAll(); setIsOpen(false) }}
              className="flex w-full items-center justify-between px-3 py-2 text-sm text-slate-300 hover:bg-slate-700"
            >
              <span>Deselect All</span>
              <span className="text-slate-500">{selectedSerials.size}</span>
            </button>

            {/* By Status */}
            {(completeCount > 0 || notInDbCount > 0) && (
              <>
                <div className="my-1 border-t border-slate-700" />
                <div className="px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-slate-500">
                  By Status
                </div>

                {/* Complete */}
                {completeCount > 0 && (
                  <>
                    <button
                      onClick={() => { onSelectComplete(); setIsOpen(false) }}
                      className="flex w-full items-center justify-between px-3 py-2 text-sm text-emerald-400 hover:bg-slate-700"
                    >
                      <span className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4" />
                        Select Complete
                      </span>
                      <span className="text-slate-500">{completeCount}</span>
                    </button>
                    <button
                      onClick={() => { onDeselectComplete(); setIsOpen(false) }}
                      className="flex w-full items-center justify-between px-3 py-2 text-sm text-emerald-400 hover:bg-slate-700"
                    >
                      <span className="flex items-center gap-2">
                        <CheckCircle className="h-4 w-4" />
                        Deselect Complete
                      </span>
                      <span className="text-slate-500">{selectedCompleteCount}</span>
                    </button>
                  </>
                )}

                {/* Not in DB - with warning styling */}
                {notInDbCount > 0 && (
                  <>
                    <button
                      onClick={() => { onSelectNotInDb(); setIsOpen(false) }}
                      className="flex w-full items-center justify-between px-3 py-2 text-sm text-amber-400 hover:bg-slate-700"
                    >
                      <span className="flex items-center gap-2">
                        <span className="text-amber-500">⚠</span>
                        Select Not in GreenLake
                      </span>
                      <span className="text-slate-500">{notInDbCount}</span>
                    </button>
                    <button
                      onClick={() => { onDeselectNotInDb(); setIsOpen(false) }}
                      className="flex w-full items-center justify-between px-3 py-2 text-sm text-amber-400 hover:bg-slate-700"
                    >
                      <span className="flex items-center gap-2">
                        <span className="text-amber-500">⚠</span>
                        Deselect Not in GreenLake
                      </span>
                      <span className="text-slate-500">{selectedNotInDbCount}</span>
                    </button>
                  </>
                )}
              </>
            )}

            {/* By Type */}
            {types.length > 0 && (
              <>
                <div className="my-1 border-t border-slate-700" />
                <div className="px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-slate-500">
                  By Type
                </div>
                {types.map(([type, counts]) => (
                  <div key={type} className="flex items-center justify-between px-3 py-1">
                    <span className="text-sm text-slate-300">{type}</span>
                    <div className="flex gap-1">
                      <button
                        onClick={() => { onSelectByType(type); setIsOpen(false) }}
                        className="rounded px-2 py-0.5 text-xs text-sky-400 hover:bg-sky-500/20"
                        title={`Select all ${type}`}
                      >
                        +{counts.total}
                      </button>
                      <button
                        onClick={() => { onDeselectByType(type); setIsOpen(false) }}
                        className="rounded px-2 py-0.5 text-xs text-rose-400 hover:bg-rose-500/20"
                        title={`Deselect all ${type}`}
                      >
                        -{counts.selected}
                      </button>
                    </div>
                  </div>
                ))}
              </>
            )}

            {/* By Model */}
            {models.length > 0 && (
              <>
                <div className="my-1 border-t border-slate-700" />
                <div className="px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-slate-500">
                  By Model
                </div>
                <div className="max-h-40 overflow-y-auto">
                  {models.map(([model, counts]) => (
                    <div key={model} className="flex items-center justify-between px-3 py-1">
                      <span className="text-sm text-slate-300 font-mono">{model}</span>
                      <div className="flex gap-1">
                        <button
                          onClick={() => { onSelectByModel(model); setIsOpen(false) }}
                          className="rounded px-2 py-0.5 text-xs text-sky-400 hover:bg-sky-500/20"
                          title={`Select all ${model}`}
                        >
                          +{counts.total}
                        </button>
                        <button
                          onClick={() => { onDeselectByModel(model); setIsOpen(false) }}
                          className="rounded px-2 py-0.5 text-xs text-rose-400 hover:bg-rose-500/20"
                          title={`Deselect all ${model}`}
                        >
                          -{counts.selected}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}

interface StatCardProps {
  label: string
  value: number
  variant?: 'default' | 'success' | 'warning' | 'info'
}

const StatCard = memo(function StatCard({ label, value, variant = 'default' }: StatCardProps) {
  const variants = {
    default: 'bg-slate-800/50 border-slate-700',
    success: 'bg-emerald-500/10 border-emerald-500/30',
    warning: 'bg-amber-500/10 border-amber-500/30',
    info: 'bg-sky-500/10 border-sky-500/30',
  }

  const textVariants = {
    default: 'text-white',
    success: 'text-emerald-400',
    warning: 'text-amber-400',
    info: 'text-sky-400',
  }

  return (
    <div
      className={`rounded-lg border p-4 ${variants[variant]}`}
      data-testid={`stat-card-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <p className="text-sm text-slate-400">{label}</p>
      <p className={`text-2xl font-bold ${textVariants[variant]}`}>{value}</p>
    </div>
  )
})
