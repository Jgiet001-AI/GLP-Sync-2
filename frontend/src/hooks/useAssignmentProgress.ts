import { useState, useCallback, useRef, useEffect } from 'react'
import type { ApplyRequest } from '../types'

// =============================================================================
// Types
// =============================================================================

export interface BatchProgressEvent {
  currentBatch: number
  totalBatches: number
  devicesInBatch: number
}

export interface TimingEvent {
  elapsedSeconds: number
  estimatedRemainingSeconds: number
  avgBatchSeconds?: number
}

export interface StatsEvent {
  successCount: number
  errorCount: number
  totalDevices: number
}

export interface ProgressEvent {
  type: 'phase_start' | 'batch_progress' | 'batch_complete' | 'phase_complete' | 'error' | 'complete'
  phase?: 'applications' | 'subscriptions' | 'tags' | 'new_devices' | 'refresh'
  batch?: BatchProgressEvent
  timing?: TimingEvent
  stats?: StatsEvent
  error?: string
  result?: unknown
}

interface UseAssignmentProgressReturn {
  progress: ProgressEvent | null
  isStreaming: boolean
  error: string | null
  startStream: (request: ApplyRequest) => Promise<unknown>
  stop: () => void
}

// =============================================================================
// Hook
// =============================================================================

/**
 * Hook for streaming assignment progress via SSE.
 *
 * Features:
 * - Proper SSE buffer handling (double-newline splitting)
 * - AbortController for cancellation
 * - Automatic cleanup on unmount
 * - Error handling with fallback support
 */
export function useAssignmentProgress(): UseAssignmentProgressReturn {
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const controllerRef = useRef<AbortController | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      controllerRef.current?.abort()
    }
  }, [])

  const startStream = useCallback(async (request: ApplyRequest): Promise<unknown> => {
    // Abort any existing stream
    controllerRef.current?.abort()

    // Reset state
    setProgress(null)
    setError(null)
    setIsStreaming(true)

    // Create new abort controller
    const controller = new AbortController()
    controllerRef.current = controller

    try {
      // Check for ReadableStream support (Safari compatibility)
      if (!('ReadableStream' in window)) {
        throw new Error('Streaming not supported in this browser')
      }

      const response = await fetch('/api/assignment/apply-stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': import.meta.env.VITE_API_KEY || '',
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`Server error: ${response.status} ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('No response body for streaming')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let finalResult: unknown = null

      try {
        while (true) {
          const { done, value } = await reader.read()

          if (done) {
            break
          }

          // Accumulate chunks into buffer, normalize CRLF to LF
          buffer += decoder.decode(value, { stream: true })
          buffer = buffer.replace(/\r\n/g, '\n')

          // Split by double newline (SSE event delimiter)
          const events = buffer.split('\n\n')
          // Keep the incomplete event (last element) in buffer
          buffer = events.pop() || ''

          // Process complete events
          for (const eventText of events) {
            if (!eventText.trim()) continue

            // Handle keep-alive comments
            if (eventText.startsWith(':')) continue

            // Parse SSE format: collect all data: lines and join them
            // This handles multi-line data correctly per SSE spec
            const dataLines = eventText
              .split('\n')
              .filter((line) => line.startsWith('data:'))
              .map((line) => line.replace(/^data:\s?/, ''))

            const data = dataLines.join('\n')

            if (data) {
              try {
                const payload = JSON.parse(data) as ProgressEvent
                setProgress(payload)

                if (payload.type === 'complete') {
                  finalResult = payload.result
                  controller.abort()
                  break
                } else if (payload.type === 'error') {
                  setError(payload.error || 'Unknown error')
                  controller.abort()
                  break
                }
              } catch (parseError) {
                console.warn('Failed to parse SSE event:', data, parseError)
              }
            }
          }
        }
      } finally {
        // Ensure reader is released
        reader.releaseLock()
      }

      setIsStreaming(false)
      return finalResult
    } catch (err) {
      // Don't report abort errors
      if (err instanceof Error && err.name === 'AbortError') {
        setIsStreaming(false)
        return null
      }

      const errorMessage = err instanceof Error ? err.message : 'Stream failed'
      setError(errorMessage)
      setIsStreaming(false)
      throw err
    }
  }, [])

  const stop = useCallback(() => {
    controllerRef.current?.abort()
    setIsStreaming(false)
  }, [])

  return {
    progress,
    isStreaming,
    error,
    startStream,
    stop,
  }
}

// =============================================================================
// Fallback Hook (for browsers without streaming support)
// =============================================================================

/**
 * Check if SSE streaming is supported in the current browser.
 */
export function isStreamingSupported(): boolean {
  return 'ReadableStream' in window && 'fetch' in window
}
