// Format date to short format (e.g., "Jan 15, 2024")
export function formatDate(dateStr: string | null): string {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

// Format full date with time
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

// Format uptime from milliseconds to human readable
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
