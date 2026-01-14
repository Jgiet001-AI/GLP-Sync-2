/**
 * Date and time formatting utilities
 *
 * Extracted from DevicesList and SubscriptionsList to reduce duplication.
 * Provides consistent date/time formatting across the application.
 */

/**
 * Format date to short format
 *
 * @param dateStr - ISO date string or null
 * @returns Formatted date string (e.g., "Jan 15, 2024") or "-" if null
 *
 * @example
 * ```tsx
 * formatDate("2024-01-15T10:30:00Z") // "Jan 15, 2024"
 * formatDate(null) // "-"
 * ```
 */
export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

/**
 * Format date with time in 12-hour format
 *
 * @param dateStr - ISO date string or null
 * @returns Formatted date and time string (e.g., "Jan 15, 2024, 10:30 AM") or "-" if null
 *
 * @example
 * ```tsx
 * formatDateTime("2024-01-15T10:30:00Z") // "Jan 15, 2024, 10:30 AM"
 * formatDateTime(null) // "-"
 * ```
 */
export function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Format uptime duration from milliseconds to human-readable string
 *
 * Automatically selects appropriate units based on duration:
 * - Days and hours for durations > 24h
 * - Hours and minutes for durations > 1h
 * - Minutes only for durations > 1m
 * - Seconds for shorter durations
 *
 * @param millis - Duration in milliseconds or null
 * @returns Human-readable duration (e.g., "5d 12h", "3h 45m", "2m", "30s") or "-" if null
 *
 * @example
 * ```tsx
 * formatUptime(432000000) // "5d 0h" (5 days)
 * formatUptime(7200000)   // "2h 0m" (2 hours)
 * formatUptime(180000)    // "3m" (3 minutes)
 * formatUptime(45000)     // "45s" (45 seconds)
 * formatUptime(null)      // "-"
 * ```
 */
export function formatUptime(millis: number | null): string {
  if (!millis) return '-'
  const seconds = Math.floor(millis / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)

  if (days > 0) {
    const remainingHours = hours % 24
    return `${days}d ${remainingHours}h`
  } else if (hours > 0) {
    const remainingMinutes = minutes % 60
    return `${hours}h ${remainingMinutes}m`
  } else if (minutes > 0) {
    return `${minutes}m`
  } else {
    return `${seconds}s`
  }
}
