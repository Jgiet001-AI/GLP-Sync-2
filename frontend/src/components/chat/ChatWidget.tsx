/**
 * Floating chat widget component.
 *
 * A collapsible chat interface that can be placed anywhere in the app.
 * Connects via WebSocket for real-time streaming responses.
 */

import { useState, useRef, useEffect, FormEvent } from 'react'
import {
  MessageCircle,
  X,
  Minimize2,
  Maximize2,
  Send,
  AlertTriangle,
  Check,
  XCircle,
  Trash2,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { useChat } from '../../hooks/useChat'
import { ChatMessage } from './ChatMessage'

interface ChatWidgetProps {
  apiBaseUrl?: string
  position?: 'bottom-right' | 'bottom-left'
}

export function ChatWidget({
  apiBaseUrl = '/api/agent',
  position = 'bottom-right',
}: ChatWidgetProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isExpanded, setIsExpanded] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    messages,
    isConnected,
    isLoading,
    error,
    pendingConfirmation,
    connect,
    disconnect,
    sendMessage,
    confirmOperation,
    cancel,
    clearConversation,
  } = useChat({ apiBaseUrl })

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  // Connect when opening
  useEffect(() => {
    if (isOpen && !isConnected) {
      connect()
    }
  }, [isOpen, isConnected, connect])

  // Focus input when opening
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (inputValue.trim() && !isLoading) {
      sendMessage(inputValue.trim())
      setInputValue('')
    }
  }

  const positionClasses =
    position === 'bottom-right' ? 'right-6 bottom-6' : 'left-6 bottom-6'

  // Closed state - just the button
  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className={`fixed ${positionClasses} z-50 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-emerald-600 text-white shadow-lg shadow-emerald-500/30 hover:shadow-xl hover:shadow-emerald-500/40 transition-all hover:scale-105`}
        aria-label="Open chat"
      >
        <MessageCircle className="h-6 w-6" />
      </button>
    )
  }

  const widgetClasses = isExpanded
    ? 'fixed inset-4 z-50'
    : `fixed ${positionClasses} z-50 w-96 h-[600px]`

  return (
    <div
      className={`${widgetClasses} flex flex-col rounded-2xl border border-slate-700/50 bg-slate-900/95 backdrop-blur-xl shadow-2xl overflow-hidden transition-all duration-200`}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-700/50 bg-slate-800/50 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-emerald-600">
            <MessageCircle className="h-5 w-5 text-white" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">GreenLake Assistant</h3>
            <div className="flex items-center gap-1.5 text-xs">
              {isConnected ? (
                <>
                  <Wifi className="h-3 w-3 text-emerald-500" />
                  <span className="text-emerald-500">Connected</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3 text-slate-500" />
                  <span className="text-slate-500">Disconnected</span>
                </>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={clearConversation}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
            aria-label="Clear conversation"
            title="Clear conversation"
          >
            <Trash2 className="h-4 w-4" />
          </button>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
            aria-label={isExpanded ? 'Minimize' : 'Expand'}
          >
            {isExpanded ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
          </button>
          <button
            onClick={() => {
              disconnect()
              setIsOpen(false)
            }}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
            aria-label="Close chat"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full p-6 text-center">
            <div className="h-16 w-16 rounded-full bg-slate-800/50 flex items-center justify-center mb-4">
              <MessageCircle className="h-8 w-8 text-slate-600" />
            </div>
            <h4 className="text-lg font-medium text-slate-300 mb-2">
              How can I help you?
            </h4>
            <p className="text-sm text-slate-500 max-w-xs">
              Ask me about devices, subscriptions, or let me help you manage your
              GreenLake inventory.
            </p>
            <div className="mt-4 flex flex-wrap gap-2 justify-center">
              {[
                'Find all switches',
                'Show expiring subscriptions',
                'List devices in us-west',
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => {
                    setInputValue(suggestion)
                    inputRef.current?.focus()
                  }}
                  className="px-3 py-1.5 text-xs bg-slate-800/50 text-slate-400 rounded-full hover:bg-slate-700/50 hover:text-slate-300 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div className="px-4 py-2 bg-red-500/10 border-t border-red-500/20 flex items-center gap-2 text-red-400 text-sm">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Confirmation dialog */}
      {pendingConfirmation && (
        <div className="px-4 py-3 bg-amber-500/10 border-t border-amber-500/20">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm text-amber-200 mb-3">
                {pendingConfirmation.message}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => confirmOperation(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 transition-colors"
                >
                  <Check className="h-4 w-4" />
                  Confirm
                </button>
                <button
                  onClick={() => confirmOperation(false)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-slate-700 text-slate-300 rounded-lg hover:bg-slate-600 transition-colors"
                >
                  <XCircle className="h-4 w-4" />
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-slate-700/50 bg-slate-800/30 p-4"
      >
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={
              isConnected ? 'Type a message...' : 'Connecting...'
            }
            disabled={!isConnected || isLoading}
            className="flex-1 rounded-xl border border-slate-700 bg-slate-800/50 px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
          />
          {isLoading ? (
            <button
              type="button"
              onClick={cancel}
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-red-600 text-white hover:bg-red-500 transition-colors"
              aria-label="Cancel"
            >
              <X className="h-5 w-5" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!inputValue.trim() || !isConnected}
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-white hover:bg-emerald-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Send message"
            >
              <Send className="h-5 w-5" />
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
