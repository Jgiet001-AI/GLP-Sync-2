/**
 * Hook to fetch application configuration from the backend.
 *
 * Returns feature flags like chatbot_enabled that control UI visibility.
 */

import { useState, useEffect } from 'react'

interface AppConfig {
  chatbot_enabled: boolean
  version: string
}

const defaultConfig: AppConfig = {
  chatbot_enabled: false,
  version: '1.0.0',
}

export function useConfig() {
  const [config, setConfig] = useState<AppConfig>(defaultConfig)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const response = await fetch('/api/config')
        if (response.ok) {
          const data = await response.json()
          setConfig(data)
        } else {
          // If config endpoint fails, assume chatbot is disabled
          console.warn('Failed to fetch config, using defaults')
        }
      } catch (err) {
        console.warn('Failed to fetch config:', err)
        setError(err instanceof Error ? err.message : 'Failed to fetch config')
      } finally {
        setIsLoading(false)
      }
    }

    fetchConfig()
  }, [])

  return { config, isLoading, error }
}
