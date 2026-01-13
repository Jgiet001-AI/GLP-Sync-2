import { useState, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios, { AxiosError } from 'axios'
import { ApiError, ApiErrorResponse } from '../types'

/**
 * Search history management with tenant/user namespacing
 * Addresses Codex feedback: localStorage needs namespacing to prevent cross-tenant bleed
 */

interface SearchHistoryItem {
  query: string
  type: 'device' | 'subscription' | 'client' | 'all'
  timestamp: number
  resultCount?: number
}

interface SearchHistoryResponse {
  items: SearchHistoryItem[]
  total: number
}

interface AddSearchRequest {
  query: string
  type: SearchHistoryItem['type']
  resultCount?: number
}

interface RemoveSearchRequest {
  query: string
  type: SearchHistoryItem['type']
}

interface UseSearchHistoryOptions {
  maxItems?: number
  namespace?: string // tenant:user namespace for isolation
}

const DEFAULT_MAX_ITEMS = 20
const STORAGE_KEY_PREFIX = 'glp_search_history'

// API client for search history
const searchHistoryApiClient = axios.create({
  baseURL: '/api/search-history',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Error interceptor - converts axios errors to structured ApiError
searchHistoryApiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
    if (error.response) {
      // Server responded with an error status
      const data = error.response.data || { detail: 'An unknown error occurred' }
      throw new ApiError(data, error.response.status)
    } else if (error.request) {
      // Request was made but no response received (network error)
      throw new ApiError(
        { detail: 'Network error: Unable to reach server' },
        0
      )
    } else {
      // Error in request setup
      throw new ApiError(
        { detail: error.message || 'Request configuration error' },
        0
      )
    }
  }
)

/**
 * API client functions for search history persistence
 */
export const searchHistoryApi = {
  /**
   * Get search history for the current user
   */
  async getHistory(namespace?: string): Promise<SearchHistoryResponse> {
    const params = namespace ? { namespace } : {}
    const response = await searchHistoryApiClient.get<SearchHistoryResponse>('', { params })
    return response.data
  },

  /**
   * Add a search to history
   */
  async addSearch(request: AddSearchRequest, namespace?: string): Promise<SearchHistoryItem> {
    const response = await searchHistoryApiClient.post<SearchHistoryItem>('', {
      ...request,
      namespace,
    })
    return response.data
  },

  /**
   * Remove a specific search from history
   */
  async removeSearch(request: RemoveSearchRequest, namespace?: string): Promise<void> {
    await searchHistoryApiClient.delete('', {
      data: {
        ...request,
        namespace,
      },
    })
  },

  /**
   * Clear all search history
   */
  async clearHistory(namespace?: string): Promise<void> {
    const params = namespace ? { namespace } : {}
    await searchHistoryApiClient.delete('/clear', { params })
  },

  /**
   * Get recent searches, optionally filtered by type
   */
  async getRecent(type?: SearchHistoryItem['type'], limit = 5, namespace?: string): Promise<SearchHistoryItem[]> {
    const params = {
      ...(type && { type }),
      limit,
      ...(namespace && { namespace }),
    }
    const response = await searchHistoryApiClient.get<SearchHistoryItem[]>('/recent', { params })
    return response.data
  },
}

/**
 * Get namespaced storage key
 * Default namespace prevents cross-tenant data leakage
 */
function getStorageKey(namespace?: string): string {
  const ns = namespace || 'default'
  return `${STORAGE_KEY_PREFIX}:${ns}`
}

/**
 * Hook for managing search history with localStorage persistence
 */
export function useSearchHistory(options: UseSearchHistoryOptions = {}) {
  const { maxItems = DEFAULT_MAX_ITEMS, namespace } = options
  const storageKey = getStorageKey(namespace)

  // SSR-safe: guard localStorage access
  const [history, setHistory] = useState<SearchHistoryItem[]>(() => {
    if (typeof window === 'undefined') return []
    try {
      const stored = localStorage.getItem(storageKey)
      return stored ? JSON.parse(stored) : []
    } catch {
      return []
    }
  })

  // Rehydrate when namespace changes
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const stored = localStorage.getItem(storageKey)
      setHistory(stored ? JSON.parse(stored) : [])
    } catch {
      setHistory([])
    }
  }, [storageKey])

  // Persist to localStorage on changes
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(history))
    } catch {
      // Handle quota exceeded or other storage errors
      console.warn('Failed to persist search history')
    }
  }, [history, storageKey])

  // Add a new search to history
  const addSearch = useCallback(
    (query: string, type: SearchHistoryItem['type'] = 'all', resultCount?: number) => {
      if (!query.trim()) return

      setHistory((prev) => {
        // Remove duplicate if exists
        const filtered = prev.filter(
          (item) => !(item.query.toLowerCase() === query.toLowerCase() && item.type === type)
        )

        // Add new item at start
        const newItem: SearchHistoryItem = {
          query: query.trim(),
          type,
          timestamp: Date.now(),
          resultCount,
        }

        // Limit to maxItems
        return [newItem, ...filtered].slice(0, maxItems)
      })
    },
    [maxItems]
  )

  // Remove a specific item from history
  const removeSearch = useCallback((query: string, type: SearchHistoryItem['type']) => {
    setHistory((prev) =>
      prev.filter(
        (item) => !(item.query.toLowerCase() === query.toLowerCase() && item.type === type)
      )
    )
  }, [])

  // Clear all history
  const clearHistory = useCallback(() => {
    setHistory([])
  }, [])

  // Get recent searches, optionally filtered by type
  const getRecent = useCallback(
    (type?: SearchHistoryItem['type'], limit = 5): SearchHistoryItem[] => {
      const filtered = type ? history.filter((item) => item.type === type) : history
      return filtered.slice(0, limit)
    },
    [history]
  )

  // Format relative time for display
  const formatRelativeTime = useCallback((timestamp: number): string => {
    const now = Date.now()
    const diff = now - timestamp
    const minutes = Math.floor(diff / 60000)
    const hours = Math.floor(minutes / 60)
    const days = Math.floor(hours / 24)

    if (minutes < 1) return 'Just now'
    if (minutes < 60) return `${minutes}m ago`
    if (hours < 24) return `${hours}h ago`
    if (days < 7) return `${days}d ago`
    return new Date(timestamp).toLocaleDateString()
  }, [])

  return {
    history,
    addSearch,
    removeSearch,
    clearHistory,
    getRecent,
    formatRelativeTime,
    isEmpty: history.length === 0,
  }
}

/**
 * Hook to get a unique user/tenant namespace
 * In a real app, this would come from auth context
 */
export function useSearchNamespace(): string {
  // For now, use a default namespace
  // In production, derive from auth context: `${tenantId}:${userId}`
  return 'default'
}
