import { useEffect, useState, useRef } from 'react'
import { CheckCircle, Loader2, XCircle, Clock, X, Zap } from 'lucide-react'
import clsx from 'clsx'

// =============================================================================
// Types
// =============================================================================

interface ProgressPhase {
  id: string
  name: string
  description: string
  estimatedSeconds?: number
}

interface BatchProgress {
  currentBatch: number
  totalBatches: number
  devicesInBatch?: number
}

interface TimingInfo {
  elapsedSeconds: number
  estimatedRemainingSeconds: number
  avgBatchSeconds?: number
}

interface StatsInfo {
  successCount: number
  errorCount: number
  totalDevices: number
}

interface ProgressModalProps {
  isOpen: boolean
  title: string
  phases: ProgressPhase[]
  currentPhaseIndex: number
  totalDevices: number
  isComplete: boolean
  isError: boolean
  errorMessage?: string
  onClose?: () => void
  onCancel?: () => void
  // New: Real-time progress from SSE
  batchProgress?: BatchProgress
  timing?: TimingInfo
  stats?: StatsInfo
  currentPhaseName?: string
}

const DEFAULT_PHASES: ProgressPhase[] = [
  {
    id: 'prepare',
    name: 'Preparing',
    description: 'Validating devices and configurations',
    estimatedSeconds: 2,
  },
  {
    id: 'applications',
    name: 'Assigning Regions',
    description: 'Setting application/region for devices',
    estimatedSeconds: 20,
  },
  {
    id: 'subscriptions',
    name: 'Assigning Subscriptions',
    description: 'Assigning licenses to devices in batches of 25',
    estimatedSeconds: 30,
  },
  {
    id: 'tags',
    name: 'Updating Tags',
    description: 'Applying tags to devices',
    estimatedSeconds: 15,
  },
  {
    id: 'new_devices',
    name: 'Adding New Devices',
    description: 'Registering new devices in GreenLake',
    estimatedSeconds: 10,
  },
  {
    id: 'complete',
    name: 'Finalizing',
    description: 'Completing the assignment process',
    estimatedSeconds: 2,
  },
]

// =============================================================================
// Main Component
// =============================================================================

export function ProgressModal({
  isOpen,
  title,
  phases = DEFAULT_PHASES,
  currentPhaseIndex,
  totalDevices,
  isComplete,
  isError,
  errorMessage,
  onClose,
  onCancel,
  // Real-time SSE data
  batchProgress,
  timing,
  stats,
  currentPhaseName,
}: ProgressModalProps) {
  const [elapsedTime, setElapsedTime] = useState(0)
  const startTimeRef = useRef<number>(Date.now())

  // Reset start time when modal opens
  useEffect(() => {
    if (isOpen) {
      startTimeRef.current = Date.now()
      setElapsedTime(0)
    }
  }, [isOpen])

  // Update elapsed time every second (fallback if no SSE timing)
  useEffect(() => {
    if (!isOpen || isComplete || isError) return

    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTimeRef.current) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [isOpen, isComplete, isError])

  // Use SSE timing if available, otherwise calculate locally
  const displayElapsedSeconds = timing?.elapsedSeconds ?? elapsedTime
  const displayRemainingSeconds = timing?.estimatedRemainingSeconds ?? calculateFallbackEta()

  function calculateFallbackEta(): number {
    // Fallback: estimate based on phases and device count
    const estimatedTotalSeconds = phases.reduce((sum, p) => sum + (p.estimatedSeconds || 0), 0)
      + Math.ceil(totalDevices / 25) * 2
    return Math.max(0, estimatedTotalSeconds - elapsedTime)
  }

  // Calculate progress percentage
  // If we have batch progress, use it for more accurate percentage
  const progressPercent = isComplete
    ? 100
    : batchProgress
      ? Math.min(95, Math.round(
          ((currentPhaseIndex * 100) / phases.length) +
          ((batchProgress.currentBatch / batchProgress.totalBatches) * (100 / phases.length))
        ))
      : Math.min(95, Math.round((currentPhaseIndex / phases.length) * 100))

  // Format time
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
  }

  if (!isOpen) return null

  // Find current phase by name if provided (from SSE)
  const currentPhaseIdx = currentPhaseName
    ? phases.findIndex(p => p.id === currentPhaseName)
    : currentPhaseIndex

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-slate-800 rounded-xl border border-slate-700 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">{title}</h2>
            <p className="text-sm text-slate-400 mt-1">
              Processing {totalDevices} device{totalDevices !== 1 ? 's' : ''}
              {stats && stats.successCount > 0 && (
                <span className="text-emerald-400 ml-2">
                  ({stats.successCount} done)
                </span>
              )}
            </p>
          </div>
          {/* Cancel button (only while running) */}
          {!isComplete && !isError && onCancel && (
            <button
              onClick={onCancel}
              className="p-1 rounded hover:bg-slate-700 transition-colors"
              aria-label="Cancel operation"
            >
              <X className="w-5 h-5 text-slate-400" />
            </button>
          )}
        </div>

        {/* Progress Bar */}
        <div className="px-6 py-4">
          <div className="flex items-center justify-between mb-2 text-sm">
            <span className="text-slate-400">Progress</span>
            <span className={clsx(
              'font-medium',
              isError ? 'text-rose-400' : isComplete ? 'text-emerald-400' : 'text-hpe-green'
            )}>
              {progressPercent}%
            </span>
          </div>
          <div className="h-3 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={clsx(
                'h-full rounded-full transition-all duration-500 ease-out',
                isError
                  ? 'bg-rose-500'
                  : isComplete
                    ? 'bg-emerald-500'
                    : 'bg-gradient-to-r from-hpe-green to-hpe-blue animate-pulse'
              )}
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          {/* Time info */}
          <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>Elapsed: {formatTime(displayElapsedSeconds)}</span>
            </div>
            {!isComplete && !isError && (
              <span>ETA: ~{formatTime(displayRemainingSeconds)}</span>
            )}
          </div>
        </div>

        {/* Batch Progress (when available from SSE) */}
        {batchProgress && !isComplete && !isError && (
          <div className="px-6 pb-4">
            <div className="p-3 bg-slate-700/50 rounded-lg">
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="text-slate-400 flex items-center gap-2">
                  <Zap className="w-4 h-4 text-hpe-green" />
                  Batch Progress
                </span>
                <span className="text-white font-medium">
                  {batchProgress.currentBatch} / {batchProgress.totalBatches}
                </span>
              </div>

              {/* Batch progress bar */}
              <div className="h-1.5 bg-slate-600 rounded-full overflow-hidden">
                <div
                  className="h-full bg-hpe-green transition-all duration-300"
                  style={{ width: `${(batchProgress.currentBatch / batchProgress.totalBatches) * 100}%` }}
                />
              </div>

              {/* Batch timing */}
              <div className="flex items-center justify-between mt-2 text-xs text-slate-500">
                {batchProgress.devicesInBatch && (
                  <span>{batchProgress.devicesInBatch} devices in batch</span>
                )}
                {timing?.avgBatchSeconds && (
                  <span>~{timing.avgBatchSeconds.toFixed(1)}s per batch</span>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Phases */}
        <div className="px-6 pb-4">
          <div className="space-y-2">
            {phases.map((phase, index) => {
              const isCurrentPhase = index === currentPhaseIdx
              const isCompleted = index < currentPhaseIdx || isComplete
              const isPending = index > currentPhaseIdx

              return (
                <div
                  key={phase.id}
                  className={clsx(
                    'flex items-center gap-3 px-3 py-2 rounded-lg transition-colors',
                    isCurrentPhase && !isError && 'bg-hpe-green/10 border border-hpe-green/20',
                    isCurrentPhase && isError && 'bg-rose-500/10 border border-rose-500/20',
                    isCompleted && !isCurrentPhase && 'opacity-60',
                    isPending && 'opacity-40'
                  )}
                >
                  {/* Status Icon */}
                  <div className="flex-shrink-0">
                    {isCompleted && !isCurrentPhase ? (
                      <CheckCircle className="w-5 h-5 text-emerald-400" />
                    ) : isCurrentPhase && isError ? (
                      <XCircle className="w-5 h-5 text-rose-400" />
                    ) : isCurrentPhase ? (
                      <Loader2 className="w-5 h-5 text-hpe-green animate-spin" />
                    ) : (
                      <div className="w-5 h-5 rounded-full border-2 border-slate-600" />
                    )}
                  </div>

                  {/* Phase Info */}
                  <div className="flex-1 min-w-0">
                    <p className={clsx(
                      'text-sm font-medium',
                      isCurrentPhase ? 'text-white' : 'text-slate-400'
                    )}>
                      {phase.name}
                    </p>
                    {isCurrentPhase && (
                      <p className="text-xs text-slate-500 truncate">
                        {phase.description}
                      </p>
                    )}
                  </div>

                  {/* Show batch count for current phase */}
                  {isCurrentPhase && batchProgress && (
                    <span className="text-xs text-slate-500">
                      {batchProgress.currentBatch}/{batchProgress.totalBatches}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Stats Summary (when available from SSE) */}
        {stats && (stats.successCount > 0 || stats.errorCount > 0) && (
          <div className="px-6 pb-4">
            <div className="flex gap-4 text-sm">
              {stats.successCount > 0 && (
                <div className="flex items-center gap-1 text-emerald-400">
                  <CheckCircle className="w-4 h-4" />
                  <span>{stats.successCount} successful</span>
                </div>
              )}
              {stats.errorCount > 0 && (
                <div className="flex items-center gap-1 text-rose-400">
                  <XCircle className="w-4 h-4" />
                  <span>{stats.errorCount} failed</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Error Message */}
        {isError && errorMessage && (
          <div className="px-6 pb-4">
            <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg">
              <p className="text-sm text-rose-400">{errorMessage}</p>
            </div>
          </div>
        )}

        {/* Footer */}
        {(isComplete || isError) && onClose && (
          <div className="px-6 py-4 border-t border-slate-700 bg-slate-800/50">
            <button
              onClick={onClose}
              className={clsx(
                'btn w-full',
                isError ? 'btn-secondary' : 'btn-primary'
              )}
            >
              {isComplete ? 'View Results' : 'Close'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// =============================================================================
// Hook to manage progress modal state
// =============================================================================

export function useProgressModal() {
  const [isOpen, setIsOpen] = useState(false)
  const [currentPhaseIndex, setCurrentPhaseIndex] = useState(0)
  const [currentPhaseName, setCurrentPhaseName] = useState<string | undefined>()
  const [isComplete, setIsComplete] = useState(false)
  const [isError, setIsError] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | undefined>()
  const [batchProgress, setBatchProgress] = useState<BatchProgress | undefined>()
  const [timing, setTiming] = useState<TimingInfo | undefined>()
  const [stats, setStats] = useState<StatsInfo | undefined>()

  const start = () => {
    setIsOpen(true)
    setCurrentPhaseIndex(0)
    setCurrentPhaseName(undefined)
    setIsComplete(false)
    setIsError(false)
    setErrorMessage(undefined)
    setBatchProgress(undefined)
    setTiming(undefined)
    setStats(undefined)
  }

  const advancePhase = () => {
    setCurrentPhaseIndex(prev => prev + 1)
    setBatchProgress(undefined)
  }

  const setPhase = (phaseName: string) => {
    setCurrentPhaseName(phaseName)
    setBatchProgress(undefined)
  }

  const updateBatchProgress = (batch: BatchProgress) => {
    setBatchProgress(batch)
  }

  const updateTiming = (newTiming: TimingInfo) => {
    setTiming(newTiming)
  }

  const updateStats = (newStats: StatsInfo) => {
    setStats(newStats)
  }

  const complete = () => {
    setIsComplete(true)
  }

  const fail = (message?: string) => {
    setIsError(true)
    setErrorMessage(message)
  }

  const close = () => {
    setIsOpen(false)
  }

  return {
    // State
    isOpen,
    currentPhaseIndex,
    currentPhaseName,
    isComplete,
    isError,
    errorMessage,
    batchProgress,
    timing,
    stats,
    // Actions
    start,
    advancePhase,
    setPhase,
    updateBatchProgress,
    updateTiming,
    updateStats,
    complete,
    fail,
    close,
  }
}

// =============================================================================
// Export types
// =============================================================================

export type { ProgressPhase, BatchProgress, TimingInfo, StatsInfo }
