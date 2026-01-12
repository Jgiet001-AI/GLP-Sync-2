/**
 * Individual chat message component.
 */

import { useState } from 'react'
import { User, Bot, ChevronDown, ChevronUp, Wrench, Loader2 } from 'lucide-react'
import type { ChatMessage as ChatMessageType } from '../../hooks/useChat'

interface ChatMessageProps {
  message: ChatMessageType
}

export function ChatMessage({ message }: ChatMessageProps) {
  const [showThinking, setShowThinking] = useState(false)
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set())

  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'

  const toggleTool = (toolId: string) => {
    setExpandedTools(prev => {
      const next = new Set(prev)
      if (next.has(toolId)) {
        next.delete(toolId)
      } else {
        next.add(toolId)
      }
      return next
    })
  }

  return (
    <div
      className={`flex gap-3 p-4 ${
        isUser ? 'bg-slate-800/50' : 'bg-slate-900/50'
      }`}
    >
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${
          isUser
            ? 'bg-emerald-600'
            : 'bg-gradient-to-br from-purple-500 to-indigo-600'
        }`}
      >
        {isUser ? (
          <User className="h-4 w-4 text-white" />
        ) : (
          <Bot className="h-4 w-4 text-white" />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Role label */}
        <div className="mb-1 text-xs font-medium text-slate-400">
          {isUser ? 'You' : 'Assistant'}
        </div>

        {/* Thinking (collapsible) */}
        {isAssistant && message.thinking && (
          <div className="mb-2">
            <button
              onClick={() => setShowThinking(!showThinking)}
              className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-400 transition-colors"
            >
              {showThinking ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
              {showThinking ? 'Hide thinking' : 'Show thinking'}
            </button>
            {showThinking && (
              <div className="mt-2 rounded-lg bg-slate-800/50 p-3 text-xs text-slate-400 italic border border-slate-700/50">
                {message.thinking}
              </div>
            )}
          </div>
        )}

        {/* Message content */}
        <div className="prose prose-invert prose-sm max-w-none">
          {message.content ? (
            <p className="text-slate-200 whitespace-pre-wrap">{message.content}</p>
          ) : message.isStreaming ? (
            <div className="flex items-center gap-2 text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Thinking...</span>
            </div>
          ) : null}
        </div>

        {/* Tool calls */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mt-3 space-y-2">
            {message.toolCalls.map((tool) => (
              <div
                key={tool.id}
                className="rounded-lg border border-slate-700/50 bg-slate-800/30 overflow-hidden"
              >
                <button
                  onClick={() => toggleTool(tool.id)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-slate-700/30 transition-colors"
                >
                  <Wrench className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                  <span className="text-sm font-medium text-slate-300">
                    {tool.name}
                  </span>
                  {tool.result ? (
                    <span className="ml-auto text-xs text-emerald-500">
                      Done
                    </span>
                  ) : (
                    <Loader2 className="ml-auto h-3 w-3 animate-spin text-slate-400" />
                  )}
                  {expandedTools.has(tool.id) ? (
                    <ChevronUp className="h-4 w-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-slate-400" />
                  )}
                </button>

                {expandedTools.has(tool.id) && (
                  <div className="border-t border-slate-700/50 p-3 space-y-2">
                    {/* Arguments */}
                    {Object.keys(tool.arguments).length > 0 && (
                      <div>
                        <div className="text-xs font-medium text-slate-400 mb-1">
                          Arguments:
                        </div>
                        <pre className="text-xs text-slate-300 bg-slate-900/50 rounded p-2 overflow-x-auto">
                          {JSON.stringify(tool.arguments, null, 2)}
                        </pre>
                      </div>
                    )}

                    {/* Result */}
                    {tool.result !== undefined && (
                      <div>
                        <div className="text-xs font-medium text-slate-400 mb-1">
                          Result:
                        </div>
                        <pre className="text-xs text-slate-300 bg-slate-900/50 rounded p-2 overflow-x-auto max-h-40">
                          {typeof tool.result === 'string'
                            ? tool.result
                            : JSON.stringify(tool.result, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Timestamp */}
        <div className="mt-2 text-xs text-slate-500">
          {message.timestamp.toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
