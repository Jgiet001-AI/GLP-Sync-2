/**
 * Chat hook for managing WebSocket connection and chat state.
 *
 * Features:
 * - JWT authentication for ticket requests
 * - Automatic reconnection with exponential backoff
 * - Heartbeat ping to keep connection alive
 * - Proper error handling and state management
 */

import { useState, useCallback, useRef, useEffect } from 'react'

// Types
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  thinking?: string
  toolCalls?: ToolCall[]
  timestamp: Date
  isStreaming?: boolean
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: unknown
}

export interface PendingConfirmation {
  operationId: string
  message: string
  riskLevel: string
}

export interface ChatState {
  messages: ChatMessage[]
  isConnected: boolean
  isConnecting: boolean
  isLoading: boolean
  error: string | null
  conversationId: string | null
  pendingConfirmation: PendingConfirmation | null
}

interface WebSocketEvent {
  type: string
  sequence: number
  content?: string
  tool_call_id?: string
  tool_name?: string
  tool_arguments?: Record<string, unknown>
  error_type?: string
  metadata?: Record<string, unknown>
}

const INITIAL_STATE: ChatState = {
  messages: [],
  isConnected: false,
  isConnecting: false,
  isLoading: false,
  error: null,
  conversationId: null,
  pendingConfirmation: null,
}

// Reconnection settings
const MAX_RECONNECT_ATTEMPTS = 5
const INITIAL_RECONNECT_DELAY = 1000 // 1 second
const MAX_RECONNECT_DELAY = 30000 // 30 seconds
const HEARTBEAT_INTERVAL = 30000 // 30 seconds

// Message validation
export const MAX_MESSAGE_LENGTH = 10000 // Maximum message length in characters

export interface UseChatOptions {
  apiBaseUrl?: string
  /**
   * JWT auth token for API requests.
   * Required in production - obtains WebSocket ticket.
   */
  authToken?: string
  /**
   * Callback to get auth token dynamically (e.g., from auth context).
   * Called when connecting if authToken is not provided.
   */
  getAuthToken?: () => string | null | Promise<string | null>
  /**
   * Whether to automatically reconnect on disconnect.
   * Default: true
   */
  autoReconnect?: boolean
}

export function useChat(options: UseChatOptions = {}) {
  const {
    apiBaseUrl = '/api/agent',
    authToken,
    getAuthToken,
    autoReconnect = true,
  } = options

  const [state, setState] = useState<ChatState>(INITIAL_STATE)
  const wsRef = useRef<WebSocket | null>(null)
  const currentMessageRef = useRef<string>('')
  const currentThinkingRef = useRef<string>('')
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const manualDisconnectRef = useRef(false)

  // Clear reconnect timeout
  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }, [])

  // Clear heartbeat interval
  const clearHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current)
      heartbeatIntervalRef.current = null
    }
  }, [])

  // Start heartbeat
  const startHeartbeat = useCallback(() => {
    clearHeartbeat()
    heartbeatIntervalRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, HEARTBEAT_INTERVAL)
  }, [clearHeartbeat])

  // Get auth token (from prop or callback)
  const resolveAuthToken = useCallback(async (): Promise<string | null> => {
    if (authToken) return authToken
    if (getAuthToken) {
      const token = await getAuthToken()
      return token
    }
    return null
  }, [authToken, getAuthToken])

  // Handle WebSocket events
  const handleWebSocketEvent = useCallback((event: WebSocketEvent) => {
    switch (event.type) {
      case 'text_delta':
        currentMessageRef.current += event.content || ''
        setState(prev => {
          const messages = [...prev.messages]
          const lastMsg = messages[messages.length - 1]
          if (lastMsg?.role === 'assistant' && lastMsg.isStreaming) {
            messages[messages.length - 1] = {
              ...lastMsg,
              content: currentMessageRef.current,
            }
          }
          return { ...prev, messages }
        })
        break

      case 'thinking_delta':
        currentThinkingRef.current += event.content || ''
        setState(prev => {
          const messages = [...prev.messages]
          const lastMsg = messages[messages.length - 1]
          if (lastMsg?.role === 'assistant' && lastMsg.isStreaming) {
            messages[messages.length - 1] = {
              ...lastMsg,
              thinking: currentThinkingRef.current,
            }
          }
          return { ...prev, messages }
        })
        break

      case 'tool_call_start':
        setState(prev => {
          const messages = [...prev.messages]
          const lastMsg = messages[messages.length - 1]
          if (lastMsg?.role === 'assistant') {
            const toolCalls = lastMsg.toolCalls || []
            toolCalls.push({
              id: event.tool_call_id || '',
              name: event.tool_name || '',
              arguments: {},
            })
            messages[messages.length - 1] = { ...lastMsg, toolCalls }
          }
          return { ...prev, messages }
        })
        break

      case 'tool_call_end':
        setState(prev => {
          const messages = [...prev.messages]
          const lastMsg = messages[messages.length - 1]
          if (lastMsg?.role === 'assistant' && lastMsg.toolCalls) {
            const toolCalls = lastMsg.toolCalls.map(tc =>
              tc.id === event.tool_call_id
                ? { ...tc, arguments: event.tool_arguments || {} }
                : tc
            )
            messages[messages.length - 1] = { ...lastMsg, toolCalls }
          }
          return { ...prev, messages }
        })
        break

      case 'tool_result':
        setState(prev => {
          const messages = [...prev.messages]
          const lastMsg = messages[messages.length - 1]
          if (lastMsg?.role === 'assistant' && lastMsg.toolCalls) {
            const toolCalls = lastMsg.toolCalls.map(tc =>
              tc.id === event.tool_call_id
                ? { ...tc, result: event.content }
                : tc
            )
            messages[messages.length - 1] = { ...lastMsg, toolCalls }
          }
          return { ...prev, messages }
        })
        break

      case 'confirmation_required':
        setState(prev => ({
          ...prev,
          pendingConfirmation: {
            operationId: event.metadata?.operation_id as string || '',
            message: event.content || 'Confirm operation?',
            riskLevel: event.metadata?.risk_level as string || 'medium',
          },
        }))
        break

      case 'done':
        setState(prev => {
          const messages = [...prev.messages]
          const lastMsg = messages[messages.length - 1]
          if (lastMsg?.role === 'assistant') {
            messages[messages.length - 1] = { ...lastMsg, isStreaming: false }
          }
          return {
            ...prev,
            messages,
            isLoading: false,
            conversationId: event.metadata?.conversation_id as string || prev.conversationId,
          }
        })
        currentMessageRef.current = ''
        currentThinkingRef.current = ''
        break

      case 'error':
        setState(prev => ({
          ...prev,
          isLoading: false,
          error: event.content || 'An error occurred',
        }))
        break

      case 'pong':
        // Heartbeat response - connection is alive
        break
    }
  }, [])

  // Connect to WebSocket
  const connect = useCallback(async () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    // Reset manual disconnect flag
    manualDisconnectRef.current = false

    setState(prev => ({ ...prev, isConnecting: true, error: null }))

    try {
      // Get auth token
      const token = await resolveAuthToken()

      // Build headers for ticket request
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }

      // Use Authorization header if token available (production)
      // In dev mode without token, backend will use dev-tenant/dev-user
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      // Get ticket for WebSocket auth
      const ticketResponse = await fetch(`${apiBaseUrl}/ticket`, {
        method: 'POST',
        headers,
      })

      if (!ticketResponse.ok) {
        const errorText = await ticketResponse.text()
        throw new Error(`Failed to get WebSocket ticket: ${ticketResponse.status} ${errorText}`)
      }

      const { ticket } = await ticketResponse.json()

      if (!ticket) {
        throw new Error('No ticket received from server')
      }

      // Connect WebSocket with ticket
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${wsProtocol}//${window.location.host}${apiBaseUrl}/ws?ticket=${ticket}`

      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0
        setState(prev => ({ ...prev, isConnected: true, isConnecting: false, error: null }))
        startHeartbeat()
      }

      ws.onclose = (event) => {
        clearHeartbeat()
        wsRef.current = null

        setState(prev => ({
          ...prev,
          isConnected: false,
          isConnecting: false,
          isLoading: false, // Reset loading state on disconnect
        }))

        // Attempt reconnection if not manual disconnect and autoReconnect enabled
        if (!manualDisconnectRef.current && autoReconnect && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = Math.min(
            INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current),
            MAX_RECONNECT_DELAY
          )

          console.log(`WebSocket closed (code: ${event.code}). Reconnecting in ${delay}ms...`)

          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current++
            connect()
          }, delay)
        } else if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          setState(prev => ({
            ...prev,
            error: 'Connection lost. Please refresh the page.',
          }))
        }
      }

      ws.onerror = () => {
        setState(prev => ({
          ...prev,
          error: 'WebSocket connection failed',
          isLoading: false,
        }))
      }

      ws.onmessage = (event) => {
        const data: WebSocketEvent = JSON.parse(event.data)
        handleWebSocketEvent(data)
      }

      wsRef.current = ws
    } catch (error) {
      setState(prev => ({
        ...prev,
        isConnecting: false,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Connection failed',
      }))
    }
  }, [apiBaseUrl, resolveAuthToken, autoReconnect, startHeartbeat, clearHeartbeat, handleWebSocketEvent])

  // Disconnect WebSocket
  const disconnect = useCallback(() => {
    manualDisconnectRef.current = true
    clearReconnectTimeout()
    clearHeartbeat()

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    setState(prev => ({
      ...prev,
      isConnected: false,
      isConnecting: false,
      isLoading: false,
    }))
  }, [clearReconnectTimeout, clearHeartbeat])

  // Send a chat message
  const sendMessage = useCallback((message: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setState(prev => ({ ...prev, error: 'Not connected' }))
      return
    }

    // Validate message length
    const trimmedMessage = message.trim()
    if (!trimmedMessage) {
      setState(prev => ({ ...prev, error: 'Message cannot be empty' }))
      return
    }

    if (message.length > MAX_MESSAGE_LENGTH) {
      setState(prev => ({
        ...prev,
        error: `Message is too long. Maximum ${MAX_MESSAGE_LENGTH} characters allowed (you have ${message.length})`,
      }))
      return
    }

    // Add user message
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: new Date(),
    }

    // Add placeholder for assistant response
    const assistantMessage: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    }

    setState(prev => ({
      ...prev,
      messages: [...prev.messages, userMessage, assistantMessage],
      isLoading: true,
      error: null,
    }))

    // Reset refs
    currentMessageRef.current = ''
    currentThinkingRef.current = ''

    // Send to WebSocket
    wsRef.current.send(JSON.stringify({
      type: 'chat',
      message,
      conversation_id: state.conversationId,
    }))
  }, [state.conversationId])

  // Confirm a pending operation
  const confirmOperation = useCallback((confirmed: boolean) => {
    if (!wsRef.current || !state.pendingConfirmation) {
      return
    }

    wsRef.current.send(JSON.stringify({
      type: 'confirm',
      operation_id: state.pendingConfirmation.operationId,
      confirmed,
    }))

    setState(prev => ({
      ...prev,
      pendingConfirmation: null,
      isLoading: confirmed,
    }))
  }, [state.pendingConfirmation])

  // Cancel current operation
  const cancel = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'cancel' }))
    }
    setState(prev => ({
      ...prev,
      isLoading: false,
      pendingConfirmation: null,
    }))
  }, [])

  // Clear conversation
  const clearConversation = useCallback(() => {
    setState(prev => ({
      ...prev,
      messages: [],
      conversationId: null,
      pendingConfirmation: null,
      error: null,
    }))
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      manualDisconnectRef.current = true
      clearReconnectTimeout()
      clearHeartbeat()
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [clearReconnectTimeout, clearHeartbeat])

  return {
    ...state,
    connect,
    disconnect,
    sendMessage,
    confirmOperation,
    cancel,
    clearConversation,
  }
}
