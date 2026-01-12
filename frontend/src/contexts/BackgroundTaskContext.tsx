import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react'

// =============================================================================
// Types
// =============================================================================

export interface BatchProgress {
  currentBatch: number
  totalBatches: number
  batchSize: number
  avgBatchTimeMs?: number
}

export interface TaskProgress {
  current: number
  total: number
  percentage: number
  phase?: string
  message?: string
  batchProgress?: BatchProgress
  estimatedRemainingMs?: number
}

export interface BackgroundTask {
  id: string
  type: 'sync' | 'clients-sync' | 'assignment' | 'fetch'
  title: string
  description?: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress?: TaskProgress
  startedAt: number // timestamp
  completedAt?: number // timestamp
  updatedAt?: number // timestamp for conflict resolution
  error?: string
  result?: unknown
}

interface BackgroundTaskState {
  tasks: BackgroundTask[]
  version: number // For storage versioning
}

type TaskAction =
  | { type: 'ADD_TASK'; payload: BackgroundTask }
  | { type: 'UPDATE_TASK'; payload: { id: string; updates: Partial<BackgroundTask> } }
  | { type: 'REMOVE_TASK'; payload: string }
  | { type: 'LOAD_TASKS'; payload: BackgroundTask[] }
  | { type: 'CLEAR_COMPLETED' }

interface BackgroundTaskContextValue {
  tasks: BackgroundTask[]
  addTask: (task: Omit<BackgroundTask, 'id' | 'startedAt'>) => string
  updateTask: (id: string, updates: Partial<BackgroundTask>) => void
  removeTask: (id: string) => void
  getTask: (id: string) => BackgroundTask | undefined
  clearCompleted: () => void
  hasRunningTasks: boolean
  runningCount: number
}

// =============================================================================
// Constants
// =============================================================================

const STORAGE_KEY = 'glp-background-tasks'
const STORAGE_VERSION = 1
const AUTO_DISMISS_DELAY = 8000 // 8 seconds

// =============================================================================
// Reducer
// =============================================================================

function taskReducer(state: BackgroundTaskState, action: TaskAction): BackgroundTaskState {
  switch (action.type) {
    case 'ADD_TASK':
      return {
        ...state,
        tasks: [...state.tasks, action.payload],
      }

    case 'UPDATE_TASK': {
      const { id, updates } = action.payload
      return {
        ...state,
        tasks: state.tasks.map((task): BackgroundTask => {
          if (task.id !== id) return task

          // Deep merge progress if both exist
          let mergedProgress = updates.progress
          if (updates.progress && task.progress) {
            mergedProgress = { ...task.progress, ...updates.progress }
          }

          return {
            ...task,
            ...updates,
            progress: mergedProgress,
            updatedAt: Date.now(),
          }
        }),
      }
    }

    case 'REMOVE_TASK':
      return {
        ...state,
        tasks: state.tasks.filter((task) => task.id !== action.payload),
      }

    case 'LOAD_TASKS':
      return {
        ...state,
        tasks: action.payload,
      }

    case 'CLEAR_COMPLETED':
      return {
        ...state,
        tasks: state.tasks.filter(
          (task) => task.status !== 'completed' && task.status !== 'failed'
        ),
      }

    default:
      return state
  }
}

// =============================================================================
// Storage helpers (with error handling for Safari private mode)
// =============================================================================

function loadFromStorage(): BackgroundTask[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return []

    const parsed = JSON.parse(stored)

    // Version check
    if (parsed.version !== STORAGE_VERSION) {
      localStorage.removeItem(STORAGE_KEY)
      return []
    }

    const now = Date.now()
    const oneHourAgo = now - 60 * 60 * 1000
    const fiveMinutesAgo = now - 5 * 60 * 1000

    // Process tasks: filter stale completed tasks, mark stale running tasks as failed
    const validTasks = (parsed.tasks || [])
      .filter((task: BackgroundTask) => {
        // Filter out stale completed tasks (completed more than 1 hour ago)
        if (task.status === 'completed' || task.status === 'failed') {
          return task.completedAt && task.completedAt > oneHourAgo
        }
        return true
      })
      .map((task: BackgroundTask) => {
        // Mark running/pending tasks as failed if they're stale (no update in 5 minutes)
        if (task.status === 'running' || task.status === 'pending') {
          const lastUpdate = task.updatedAt || task.startedAt
          if (lastUpdate < fiveMinutesAgo) {
            return {
              ...task,
              status: 'failed' as const,
              error: 'Task was interrupted (browser closed or refreshed)',
              completedAt: now,
            }
          }
        }
        return task
      })

    return validTasks
  } catch {
    // Safari private mode or corrupted data
    return []
  }
}

function saveToStorage(tasks: BackgroundTask[]): void {
  try {
    const data = {
      version: STORAGE_VERSION,
      tasks,
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch {
    // Safari private mode or quota exceeded - silently ignore
  }
}

// =============================================================================
// Context
// =============================================================================

const BackgroundTaskContext = createContext<BackgroundTaskContextValue | null>(null)

export function useBackgroundTasks(): BackgroundTaskContextValue {
  const context = useContext(BackgroundTaskContext)
  if (!context) {
    throw new Error('useBackgroundTasks must be used within BackgroundTaskProvider')
  }
  return context
}

// =============================================================================
// Provider
// =============================================================================

interface BackgroundTaskProviderProps {
  children: ReactNode
}

// Generate unique ID with fallback for browsers without crypto.randomUUID
function generateTaskId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  // Fallback for older browsers/insecure contexts
  return `task-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function BackgroundTaskProvider({ children }: BackgroundTaskProviderProps) {
  // Lazy initialization - load from storage synchronously to avoid race conditions
  const [state, dispatch] = useReducer(taskReducer, undefined, () => ({
    tasks: loadFromStorage(),
    version: STORAGE_VERSION,
  }))

  // Debounce timer for storage writes
  const saveTimerRef = useRef<number | null>(null)

  // Debounced save to storage (250ms idle)
  useEffect(() => {
    if (saveTimerRef.current) {
      window.clearTimeout(saveTimerRef.current)
    }

    saveTimerRef.current = window.setTimeout(() => {
      saveToStorage(state.tasks)
    }, 250)

    return () => {
      if (saveTimerRef.current) {
        window.clearTimeout(saveTimerRef.current)
      }
    }
  }, [state.tasks])

  // Cross-tab synchronization
  useEffect(() => {
    const handleStorageChange = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY && event.newValue) {
        try {
          const parsed = JSON.parse(event.newValue)
          if (parsed.version === STORAGE_VERSION && Array.isArray(parsed.tasks)) {
            // Merge tasks by ID, preferring newer updates
            dispatch({ type: 'LOAD_TASKS', payload: parsed.tasks })
          }
        } catch {
          // Ignore parse errors
        }
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  // Actions
  const addTask = useCallback(
    (task: Omit<BackgroundTask, 'id' | 'startedAt'>): string => {
      const id = generateTaskId()
      const now = Date.now()
      const newTask: BackgroundTask = {
        ...task,
        id,
        startedAt: now,
        updatedAt: now,
      }
      dispatch({ type: 'ADD_TASK', payload: newTask })
      return id
    },
    []
  )

  const updateTask = useCallback(
    (id: string, updates: Partial<BackgroundTask>) => {
      dispatch({ type: 'UPDATE_TASK', payload: { id, updates } })
    },
    []
  )

  const removeTask = useCallback((id: string) => {
    dispatch({ type: 'REMOVE_TASK', payload: id })
  }, [])

  const getTask = useCallback(
    (id: string): BackgroundTask | undefined => {
      return state.tasks.find((task) => task.id === id)
    },
    [state.tasks]
  )

  const clearCompleted = useCallback(() => {
    dispatch({ type: 'CLEAR_COMPLETED' })
  }, [])

  // Derived state
  const runningTasks = state.tasks.filter(
    (t) => t.status === 'running' || t.status === 'pending'
  )
  const hasRunningTasks = runningTasks.length > 0
  const runningCount = runningTasks.length

  const contextValue: BackgroundTaskContextValue = {
    tasks: state.tasks,
    addTask,
    updateTask,
    removeTask,
    getTask,
    clearCompleted,
    hasRunningTasks,
    runningCount,
  }

  return (
    <BackgroundTaskContext.Provider value={contextValue}>
      {children}
    </BackgroundTaskContext.Provider>
  )
}

// =============================================================================
// Export auto-dismiss delay for use in indicator
// =============================================================================

export { AUTO_DISMISS_DELAY }
