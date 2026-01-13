/**
 * Debounced search value hook
 *
 * Extracted from DevicesList and SubscriptionsList pages to reduce duplication.
 * Provides a way to delay processing of rapidly changing values (e.g., search input)
 * to avoid expensive operations like API calls on every keystroke.
 */

import { useState, useEffect } from 'react'

/**
 * Debounce a rapidly changing value with configurable delay
 *
 * Returns a delayed version of the input value that only updates after the
 * specified delay has elapsed since the last change. This is particularly
 * useful for search inputs where you want to wait until the user stops
 * typing before triggering an API call or expensive computation.
 *
 * How it works:
 * - On each value change, starts a timer
 * - If value changes again before timer expires, cancels old timer and starts new one
 * - Only updates the debounced value when timer completes without interruption
 * - Cleanup function ensures timers are cancelled when component unmounts
 *
 * @template T - Type of the value being debounced
 * @param value - The value to debounce (typically from user input)
 * @param delay - Delay in milliseconds before updating debounced value (default: 300ms)
 * @returns The debounced value that updates after the delay period
 *
 * @example
 * ```tsx
 * // Basic search input debouncing
 * const [searchInput, setSearchInput] = useState('')
 * const debouncedSearch = useDebouncedSearch(searchInput, 300)
 *
 * // API call only triggers 300ms after user stops typing
 * useEffect(() => {
 *   if (debouncedSearch) {
 *     fetchResults(debouncedSearch)
 *   }
 * }, [debouncedSearch])
 *
 * return (
 *   <input
 *     value={searchInput}
 *     onChange={(e) => setSearchInput(e.target.value)}
 *     placeholder="Search..."
 *   />
 * )
 * ```
 *
 * @example
 * ```tsx
 * // Custom delay for slower API
 * const debouncedSlowSearch = useDebouncedSearch(searchInput, 500)
 *
 * // Debounce numbers (e.g., slider values)
 * const [sliderValue, setSliderValue] = useState(50)
 * const debouncedSliderValue = useDebouncedSearch(sliderValue, 200)
 * ```
 */
export function useDebouncedSearch<T>(value: T, delay = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    // Set up timer to update debounced value after delay
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    // Cancel timer if value changes or component unmounts
    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}
