import { memo, useEffect, useRef, useCallback } from 'react'
import { X, CheckCircle, XCircle, Loader2, Clock, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { useBackgroundTasks, AUTO_DISMISS_DELAY, type BackgroundTask } from '../contexts/BackgroundTaskContext'

// =============================================================================
// Main Indicator Component
// =============================================================================

export function BackgroundTaskIndicator() {
  const { tasks, removeTask, clearCompleted } = useBackgroundTasks()

  // Track auto-dismiss timers to prevent memory leaks
  const timersRef = useRef<Map<string, number>>(new Map())

  // Clear all timers on unmount
  useEffect(() => {
    return () => {
      timersRef.current.forEach((timerId) => window.clearTimeout(timerId))
      timersRef.current.clear()
    }
  }, [])

  // Auto-dismiss completed/failed tasks
  useEffect(() => {
    const completedTasks = tasks.filter(
      (t) => (t.status === 'completed' || t.status === 'failed') && !timersRef.current.has(t.id)
    )

    completedTasks.forEach((task) => {
      const timerId = window.setTimeout(() => {
        removeTask(task.id)
        timersRef.current.delete(task.id)
      }, AUTO_DISMISS_DELAY)

      timersRef.current.set(task.id, timerId)
    })

    // Clear timers for tasks that no longer exist
    timersRef.current.forEach((timerId, taskId) => {
      if (!tasks.find((t) => t.id === taskId)) {
        window.clearTimeout(timerId)
        timersRef.current.delete(taskId)
      }
    })
  }, [tasks, removeTask])

  // Handle manual dismiss
  const handleDismiss = useCallback(
    (taskId: string) => {
      // Clear any pending auto-dismiss timer
      const timerId = timersRef.current.get(taskId)
      if (timerId) {
        window.clearTimeout(timerId)
        timersRef.current.delete(taskId)
      }
      removeTask(taskId)
    },
    [removeTask]
  )

  // Don't render if no tasks
  if (tasks.length === 0) return null

  const runningTasks = tasks.filter((t) => t.status === 'running' || t.status === 'pending')
  const completedTasks = tasks.filter((t) => t.status === 'completed' || t.status === 'failed')

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm"
      role="region"
      aria-label="Background tasks"
      aria-live="polite"
    >
      {/* Running tasks */}
      {runningTasks.map((task) => (
        <TaskCard key={task.id} task={task} onDismiss={handleDismiss} />
      ))}

      {/* Completed tasks (show up to 3) */}
      {completedTasks.slice(0, 3).map((task) => (
        <TaskCard key={task.id} task={task} onDismiss={handleDismiss} />
      ))}

      {/* Clear all button when there are multiple completed */}
      {completedTasks.length > 1 && (
        <button
          onClick={clearCompleted}
          className="self-end text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          Clear all completed
        </button>
      )}
    </div>
  )
}

// =============================================================================
// Task Card Component
// =============================================================================

interface TaskCardProps {
  task: BackgroundTask
  onDismiss: (id: string) => void
}

const TaskCard = memo(function TaskCard({ task, onDismiss }: TaskCardProps) {
  const isRunning = task.status === 'running' || task.status === 'pending'
  const isCompleted = task.status === 'completed'
  const isFailed = task.status === 'failed'

  // Calculate elapsed time
  const elapsed = Date.now() - task.startedAt
  const elapsedStr = formatDuration(elapsed)

  // Get ETA from progress
  const eta = task.progress?.estimatedRemainingMs
  const etaStr = eta ? formatDuration(eta) : null

  return (
    <div
      className={clsx(
        'rounded-lg border shadow-lg backdrop-blur-sm p-3 min-w-[280px] transition-all duration-300',
        isRunning && 'bg-slate-800/95 border-slate-600',
        isCompleted && 'bg-emerald-900/90 border-emerald-600/50',
        isFailed && 'bg-rose-900/90 border-rose-600/50'
      )}
    >
      {/* Header row */}
      <div className="flex items-start gap-3">
        {/* Status icon */}
        <div className="flex-shrink-0 mt-0.5">
          {isRunning && (
            <Loader2 className="w-5 h-5 text-hpe-green animate-spin" aria-hidden="true" />
          )}
          {isCompleted && (
            <CheckCircle className="w-5 h-5 text-emerald-400" aria-hidden="true" />
          )}
          {isFailed && (
            <XCircle className="w-5 h-5 text-rose-400" aria-hidden="true" />
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{task.title}</p>
          {task.description && (
            <p className="text-xs text-slate-400 mt-0.5 truncate">{task.description}</p>
          )}
        </div>

        {/* Dismiss button */}
        <button
          onClick={() => onDismiss(task.id)}
          className="flex-shrink-0 p-1 rounded hover:bg-slate-700/50 transition-colors"
          aria-label="Dismiss notification"
        >
          <X className="w-4 h-4 text-slate-500" />
        </button>
      </div>

      {/* Progress bar (for running tasks with progress) */}
      {isRunning && task.progress && (
        <div className="mt-3">
          {/* Phase info */}
          {task.progress.phase && (
            <p className="text-xs text-slate-400 mb-1 flex items-center gap-1">
              <ChevronRight className="w-3 h-3" />
              {task.progress.phase}
              {task.progress.message && (
                <span className="text-slate-500">- {task.progress.message}</span>
              )}
            </p>
          )}

          {/* Progress bar */}
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-hpe-green to-hpe-blue transition-all duration-300"
              style={{ width: `${Math.min(task.progress.percentage, 100)}%` }}
            />
          </div>

          {/* Batch progress details */}
          {task.progress.batchProgress && (
            <div className="flex justify-between mt-1.5 text-xs text-slate-500">
              <span>
                Batch {task.progress.batchProgress.currentBatch} / {task.progress.batchProgress.totalBatches}
              </span>
              {task.progress.batchProgress.avgBatchTimeMs && (
                <span>~{(task.progress.batchProgress.avgBatchTimeMs / 1000).toFixed(1)}s/batch</span>
              )}
            </div>
          )}

          {/* Time info */}
          <div className="flex justify-between mt-1 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {elapsedStr}
            </span>
            {etaStr && <span>ETA: ~{etaStr}</span>}
          </div>
        </div>
      )}

      {/* Error message */}
      {isFailed && task.error && (
        <p className="mt-2 text-xs text-rose-300 bg-rose-950/50 rounded p-2">
          {task.error}
        </p>
      )}

      {/* Completion time */}
      {(isCompleted || isFailed) && task.completedAt && (
        <p className="mt-2 text-xs text-slate-500">
          {isCompleted ? 'Completed' : 'Failed'} in {formatDuration(task.completedAt - task.startedAt)}
        </p>
      )}
    </div>
  )
})

// =============================================================================
// Helpers
// =============================================================================

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`

  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60

  if (minutes < 60) {
    return remainingSeconds > 0 ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  }

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}
