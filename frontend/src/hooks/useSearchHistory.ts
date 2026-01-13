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
 * Hook for managing search history with backend sync and localStorage cache
 */
export function useSearchHistory(options: UseSearchHistoryOptions = {}) {
  const { maxItems = DEFAULT_MAX_ITEMS, namespace } = options
  const storageKey = getStorageKey(namespace)
  const queryClient = useQueryClient()

  // SSR-safe: guard localStorage access for initial state
  const [localHistory, setLocalHistory] = useState<SearchHistoryItem[]>(() => {
    if (typeof window === 'undefined') return []
    try {
      const stored = localStorage.getItem(storageKey)
      return stored ? JSON.parse(stored) : []
    } catch {
      return []
    }
  })

  // Fetch history from backend
  const { data: backendData, isLoading, error } = useQuery({
    queryKey: ['searchHistory', namespace],
    queryFn: () => searchHistoryApi.getHistory(namespace),
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes
    retry: 1,
  })

  // Sync backend data to localStorage when it changes
  useEffect(() => {
    if (backendData?.items) {
      setLocalHistory(backendData.items)
      try {
        localStorage.setItem(storageKey, JSON.stringify(backendData.items))
      } catch {
        // Handle quota exceeded or other storage errors
      }
    }
  }, [backendData, storageKey])

  // Use backend data if available, fallback to localStorage
  const history = backendData?.items || localHistory

  // Add search mutation
  const addSearchMutation = useMutation({
    mutationFn: (request: AddSearchRequest) =>
      searchHistoryApi.addSearch(request, namespace),
    onMutate: async (request) => {
      // Cancel outgoing queries
      await queryClient.cancelQueries({ queryKey: ['searchHistory', namespace] })

      // Snapshot previous value
      const previous = queryClient.getQueryData(['searchHistory', namespace])

      // Optimistically update
      const newItem: SearchHistoryItem = {
        query: request.query.trim(),
        type: request.type,
        timestamp: Date.now(),
        resultCount: request.resultCount,
      }

      queryClient.setQueryData(['searchHistory', namespace], (old: SearchHistoryResponse | undefined) => {
        if (!old) return { items: [newItem], total: 1 }

        const filtered = old.items.filter(
          (item) => !(item.query.toLowerCase() === newItem.query.toLowerCase() && item.type === newItem.type)
        )

        return {
          items: [newItem, ...filtered].slice(0, maxItems),
          total: Math.min(filtered.length + 1, maxItems),
        }
      })

      return { previous }
    },
    onError: (_err, _request, context) => {
      // Rollback on error
      if (context?.previous) {
        queryClient.setQueryData(['searchHistory', namespace], context.previous)
      }
    },
    onSettled: () => {
      // Refetch to ensure sync
      queryClient.invalidateQueries({ queryKey: ['searchHistory', namespace] })
    },
  })

  // Remove search mutation
  const removeSearchMutation = useMutation({
    mutationFn: (request: RemoveSearchRequest) =>
      searchHistoryApi.removeSearch(request, namespace),
    onMutate: async (request) => {
      await queryClient.cancelQueries({ queryKey: ['searchHistory', namespace] })
      const previous = queryClient.getQueryData(['searchHistory', namespace])

      queryClient.setQueryData(['searchHistory', namespace], (old: SearchHistoryResponse | undefined) => {
        if (!old) return old

        const filtered = old.items.filter(
          (item) => !(item.query.toLowerCase() === request.query.toLowerCase() && item.type === request.type)
        )

        return {
          items: filtered,
          total: filtered.length,
        }
      })

      return { previous }
    },
    onError: (_err, _request, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['searchHistory', namespace], context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['searchHistory', namespace] })
    },
  })

  // Clear history mutation
  const clearHistoryMutation = useMutation({
    mutationFn: () => searchHistoryApi.clearHistory(namespace),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['searchHistory', namespace] })
      const previous = queryClient.getQueryData(['searchHistory', namespace])

      queryClient.setQueryData(['searchHistory', namespace], {
        items: [],
        total: 0,
      })

      return { previous }
    },
    onError: (_err, _request, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['searchHistory', namespace], context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['searchHistory', namespace] })
    },
  })

  // Add a new search to history
  const addSearch = useCallback(
    (query: string, type: SearchHistoryItem['type'] = 'all', resultCount?: number) => {
      if (!query.trim()) return
      addSearchMutation.mutate({ query: query.trim(), type, resultCount })
    },
    [addSearchMutation]
  )

  // Remove a specific item from history
  const removeSearch = useCallback(
    (query: string, type: SearchHistoryItem['type']) => {
      removeSearchMutation.mutate({ query, type })
    },
    [removeSearchMutation]
  )

  // Clear all history
  const clearHistory = useCallback(() => {
    clearHistoryMutation.mutate()
  }, [clearHistoryMutation])

  // Get recent searches, optionally filtered by type
  const getRecent = useCallback(
    (type?: SearchHistoryItem['type'], limit = 5): SearchHistoryItem[] => {
      const filtered = type ? history.filter((item) => item.type === type) : history
      return filtered.slice(0, limit)
    },
    [history]
  )

  // Get search suggestions based on partial query match
  const getSuggestions = useCallback(
    (partialQuery: string, type?: SearchHistoryItem['type'], limit = 5): SearchHistoryItem[] => {
      if (!partialQuery.trim()) return []

      const query = partialQuery.toLowerCase().trim()
      const filtered = history.filter((item) => {
        const matchesQuery = item.query.toLowerCase().includes(query)
        const matchesType = !type || item.type === type
        return matchesQuery && matchesType
      })

      // Sort by relevance: exact matches first, then by recency
      return filtered
        .sort((a, b) => {
          const aStartsWith = a.query.toLowerCase().startsWith(query)
          const bStartsWith = b.query.toLowerCase().startsWith(query)

          if (aStartsWith && !bStartsWith) return -1
          if (!aStartsWith && bStartsWith) return 1

          // If both start with query or neither does, sort by recency
          return b.timestamp - a.timestamp
        })
        .slice(0, limit)
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
    getSuggestions,
    formatRelativeTime,
    isEmpty: history.length === 0,
    isLoading,
    error,
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
