import { useState, useEffect } from 'react'

/**
 * Hook to debounce a search value with configurable delay
 *
 * Extracted from DevicesList and SubscriptionsList pages to reduce duplication.
 * Useful for search inputs where you want to delay API calls until the user
 * stops typing.
 *
 * @param value - The value to debounce (typically search input)
 * @param delay - Delay in milliseconds (default: 300ms)
 * @returns The debounced value
 *
 * @example
 * ```tsx
 * const [searchInput, setSearchInput] = useState('')
 * const debouncedSearch = useDebouncedSearch(searchInput, 300)
 *
 * useEffect(() => {
 *   // This will only run 300ms after user stops typing
 *   fetchResults(debouncedSearch)
 * }, [debouncedSearch])
 * ```
 */
export function useDebouncedSearch<T>(value: T, delay = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}
