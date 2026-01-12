import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Hook for bidirectional URL state synchronization
 * Addresses Codex feedback: deterministic serialization with sorted keys
 */

type SerializableValue = string | number | boolean | null | undefined
type SerializableArray = SerializableValue[]
type SerializableObject = Record<string, SerializableValue | SerializableArray>

/**
 * Parse a URL search param value back to its original type
 */
function parseValue<T>(value: string | null, defaultValue: T): T {
  if (value === null) return defaultValue

  // Try to parse as JSON for arrays/objects
  if (value.startsWith('[') || value.startsWith('{')) {
    try {
      return JSON.parse(value) as T
    } catch {
      return value as T
    }
  }

  // Parse booleans
  if (value === 'true') return true as T
  if (value === 'false') return false as T

  // Parse numbers
  if (/^-?\d+(\.\d+)?$/.test(value)) {
    const num = parseFloat(value)
    if (!isNaN(num)) return num as T
  }

  return value as T
}

/**
 * Serialize a value for URL param storage
 * Uses deterministic JSON stringify with sorted keys for cache consistency
 */
function serializeValue(value: SerializableValue | SerializableArray | SerializableObject): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)

  // Sort object keys for deterministic output (Codex recommendation)
  // Clone array before sorting to avoid mutating input
  if (Array.isArray(value)) {
    return JSON.stringify([...value].sort())
  }

  if (typeof value === 'object') {
    const sorted = Object.keys(value)
      .sort()
      .reduce((acc, key) => {
        acc[key] = value[key]
        return acc
      }, {} as SerializableObject)
    return JSON.stringify(sorted)
  }

  return String(value)
}

/**
 * Single URL param state hook
 */
export function useUrlParam<T extends SerializableValue>(
  key: string,
  defaultValue: T
): [T, (value: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const value = useMemo(() => {
    return parseValue(searchParams.get(key), defaultValue)
  }, [searchParams, key, defaultValue])

  const setValue = useCallback(
    (newValue: T) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          const serialized = serializeValue(newValue as SerializableValue)

          if (serialized === '' || serialized === serializeValue(defaultValue as SerializableValue)) {
            next.delete(key)
          } else {
            next.set(key, serialized)
          }
          return next
        },
        { replace: true }
      )
    },
    [key, defaultValue, setSearchParams]
  )

  return [value, setValue]
}

/**
 * Multi-param URL state hook for complex filter states
 * Maintains bidirectional sync with URL search params
 */
export function useUrlState<T extends Record<string, SerializableValue | SerializableArray>>(
  defaultState: T
): [T, (updates: Partial<T>) => void, () => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  // Derive state from URL params (Codex recommendation: single source of truth)
  const state = useMemo(() => {
    const result = { ...defaultState }

    for (const key of Object.keys(defaultState)) {
      const urlValue = searchParams.get(key)
      if (urlValue !== null) {
        result[key as keyof T] = parseValue(urlValue, defaultState[key]) as T[keyof T]
      }
    }

    return result
  }, [searchParams, defaultState])

  // Update specific params
  const setState = useCallback(
    (updates: Partial<T>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)

          for (const [key, value] of Object.entries(updates)) {
            const serialized = serializeValue(value as SerializableValue)
            const defaultSerialized = serializeValue(defaultState[key as keyof T] as SerializableValue)

            if (serialized === '' || serialized === defaultSerialized) {
              next.delete(key)
            } else {
              next.set(key, serialized)
            }
          }

          return next
        },
        { replace: true }
      )
    },
    [defaultState, setSearchParams]
  )

  // Clear all params to defaults
  const clearState = useCallback(() => {
    setSearchParams({}, { replace: true })
  }, [setSearchParams])

  return [state, setState, clearState]
}

/**
 * Hook for array-based multi-select URL params
 * e.g., ?device_types=AP,SWITCH,GATEWAY
 */
export function useUrlArrayParam(
  key: string,
  defaultValue: string[] = []
): [string[], (values: string[]) => void, (value: string) => void, (value: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const values = useMemo(() => {
    const param = searchParams.get(key)
    if (!param) return defaultValue
    return param.split(',').filter(Boolean).sort()
  }, [searchParams, key, defaultValue])

  const setValues = useCallback(
    (newValues: string[]) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          const sorted = [...newValues].filter(Boolean).sort()

          // Clone defaultValue before sorting to avoid mutation
          if (sorted.length === 0 || JSON.stringify(sorted) === JSON.stringify([...defaultValue].sort())) {
            next.delete(key)
          } else {
            next.set(key, sorted.join(','))
          }
          return next
        },
        { replace: true }
      )
    },
    [key, defaultValue, setSearchParams]
  )

  const addValue = useCallback(
    (value: string) => {
      if (!values.includes(value)) {
        setValues([...values, value])
      }
    },
    [values, setValues]
  )

  const removeValue = useCallback(
    (value: string) => {
      setValues(values.filter((v) => v !== value))
    },
    [values, setValues]
  )

  return [values, setValues, addValue, removeValue]
}

/**
 * Generate a shareable URL with current state
 * SSR-safe: guards against window access during server rendering
 */
export function useShareableUrl(): string {
  const [searchParams] = useSearchParams()
  return useMemo(() => {
    if (typeof window === 'undefined') return ''
    const url = new URL(window.location.href)
    url.search = searchParams.toString()
    return url.toString()
  }, [searchParams])
}

/**
 * Parse filter state from URL for React Query cache keys
 * Returns a stable, deterministic string for cache keying
 * Sorts by [key, value] pairs and URL-encodes values for stability
 */
export function useFilterCacheKey(prefix: string): string {
  const [searchParams] = useSearchParams()
  return useMemo(() => {
    const params = Array.from(searchParams.entries())
      .sort(([aKey, aVal], [bKey, bVal]) => {
        const keyCompare = aKey.localeCompare(bKey)
        return keyCompare !== 0 ? keyCompare : aVal.localeCompare(bVal)
      })
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&')
    return `${prefix}:${params || 'default'}`
  }, [searchParams, prefix])
}
