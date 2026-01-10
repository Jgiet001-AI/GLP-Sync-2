import { useEffect, useState } from 'react'
import { CheckCircle, Loader2, XCircle, Clock } from 'lucide-react'
import clsx from 'clsx'

interface ProgressPhase {
  id: string
  name: string
  description: string
  estimatedSeconds?: number
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
}

const DEFAULT_PHASES: ProgressPhase[] = [
  {
    id: 'prepare',
    name: 'Preparing',
    description: 'Validating devices and configurations',
    estimatedSeconds: 2,
  },
  {
    id: 'subscriptions',
    name: 'Assigning Subscriptions',
    description: 'Assigning licenses to devices in batches of 25',
    estimatedSeconds: 30,
  },
  {
    id: 'applications',
    name: 'Assigning Regions',
    description: 'Setting application/region for devices',
    estimatedSeconds: 20,
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
}: ProgressModalProps) {
  const [elapsedTime, setElapsedTime] = useState(0)
  const [startTime] = useState(() => Date.now())

  // Update elapsed time every second
  useEffect(() => {
    if (!isOpen || isComplete || isError) return

    const interval = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000))
    }, 1000)

    return () => clearInterval(interval)
  }, [isOpen, isComplete, isError, startTime])

  // Calculate estimated total time based on device count
  const estimatedTotalSeconds = phases.reduce((sum, p) => sum + (p.estimatedSeconds || 0), 0)
    + Math.ceil(totalDevices / 25) * 2 // Extra time for batching

  // Calculate progress percentage
  const completedPhases = currentPhaseIndex
  const progressPercent = isComplete
    ? 100
    : Math.min(95, Math.round((completedPhases / phases.length) * 100))

  // Format time
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return mins > 0 ? `${mins}m ${secs}s` : `${secs}s`
  }

  // Estimated remaining time
  const estimatedRemaining = Math.max(0, estimatedTotalSeconds - elapsedTime)

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-slate-800 rounded-xl border border-slate-700 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700">
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          <p className="text-sm text-slate-400 mt-1">
            Processing {totalDevices} device{totalDevices !== 1 ? 's' : ''}
          </p>
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
              <span>Elapsed: {formatTime(elapsedTime)}</span>
            </div>
            {!isComplete && !isError && (
              <span>Est. remaining: ~{formatTime(estimatedRemaining)}</span>
            )}
          </div>
        </div>

        {/* Phases */}
        <div className="px-6 pb-4">
          <div className="space-y-2">
            {phases.map((phase, index) => {
              const isCurrentPhase = index === currentPhaseIndex
              const isCompleted = index < currentPhaseIndex || isComplete
              const isPending = index > currentPhaseIndex

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
                </div>
              )
            })}
          </div>
        </div>

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

// Hook to manage progress modal state
export function useProgressModal() {
  const [isOpen, setIsOpen] = useState(false)
  const [currentPhaseIndex, setCurrentPhaseIndex] = useState(0)
  const [isComplete, setIsComplete] = useState(false)
  const [isError, setIsError] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | undefined>()

  const start = () => {
    setIsOpen(true)
    setCurrentPhaseIndex(0)
    setIsComplete(false)
    setIsError(false)
    setErrorMessage(undefined)
  }

  const advancePhase = () => {
    setCurrentPhaseIndex(prev => prev + 1)
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
    isOpen,
    currentPhaseIndex,
    isComplete,
    isError,
    errorMessage,
    start,
    advancePhase,
    complete,
    fail,
    close,
  }
}
