/**
 * Individual chat message component.
 *
 * Renders markdown content and shows a friendly "thinking" indicator
 * when the AI is processing (instead of showing raw tool calls).
 */

import { useState } from 'react'
import { User, Bot, ChevronDown, ChevronUp, Loader2, Brain } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMessage as ChatMessageType } from '../../hooks/useChat'

interface ChatMessageProps {
  message: ChatMessageType
}

export function ChatMessage({ message }: ChatMessageProps) {
  const [showThinking, setShowThinking] = useState(false)

  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'

  // Check if there are any pending tool calls (still processing)
  const hasPendingToolCalls = message.toolCalls?.some(tc => !tc.result)
  // Check if all tool calls are complete
  const hasCompletedToolCalls = message.toolCalls && message.toolCalls.length > 0 && !hasPendingToolCalls

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

        {/* Thinking indicator (shown while tool calls are in progress) */}
        {isAssistant && hasPendingToolCalls && (
          <div className="mb-3 flex items-center gap-2 rounded-lg bg-slate-800/50 px-3 py-2 border border-slate-700/50">
            <Brain className="h-4 w-4 text-purple-400 animate-pulse" />
            <span className="text-sm text-slate-300">Analyzing your request...</span>
            <Loader2 className="h-3 w-3 animate-spin text-slate-400 ml-auto" />
          </div>
        )}

        {/* Thinking content (collapsible - only shown after completion) */}
        {isAssistant && message.thinking && hasCompletedToolCalls && (
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
              {showThinking ? 'Hide analysis details' : 'Show analysis details'}
            </button>
            {showThinking && (
              <div className="mt-2 rounded-lg bg-slate-800/50 p-3 text-xs text-slate-400 italic border border-slate-700/50">
                {message.thinking}
              </div>
            )}
          </div>
        )}

        {/* Message content with markdown rendering */}
        <div className="prose prose-invert prose-sm max-w-none">
          {message.content ? (
            <div className="text-slate-200 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Style headings
                  h1: ({ children }) => <h1 className="text-lg font-bold text-slate-100 mt-4 mb-2">{children}</h1>,
                  h2: ({ children }) => <h2 className="text-base font-semibold text-slate-100 mt-3 mb-2">{children}</h2>,
                  h3: ({ children }) => <h3 className="text-sm font-semibold text-slate-200 mt-2 mb-1">{children}</h3>,
                  // Style paragraphs
                  p: ({ children }) => <p className="text-slate-200 mb-2 leading-relaxed">{children}</p>,
                  // Style lists
                  ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1 text-slate-200">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1 text-slate-200">{children}</ol>,
                  li: ({ children }) => <li className="text-slate-200">{children}</li>,
                  // Style code
                  code: ({ className, children }) => {
                    const isInline = !className
                    return isInline ? (
                      <code className="bg-slate-800 px-1.5 py-0.5 rounded text-emerald-400 text-xs font-mono">{children}</code>
                    ) : (
                      <code className="block bg-slate-800 p-3 rounded-lg text-slate-300 text-xs font-mono overflow-x-auto">{children}</code>
                    )
                  },
                  pre: ({ children }) => <pre className="bg-slate-800 p-3 rounded-lg overflow-x-auto mb-2">{children}</pre>,
                  // Style links
                  a: ({ href, children }) => (
                    <a href={href} className="text-emerald-400 hover:text-emerald-300 underline" target="_blank" rel="noopener noreferrer">
                      {children}
                    </a>
                  ),
                  // Style bold/italic
                  strong: ({ children }) => <strong className="font-semibold text-slate-100">{children}</strong>,
                  em: ({ children }) => <em className="italic text-slate-300">{children}</em>,
                  // Style tables
                  table: ({ children }) => (
                    <div className="overflow-x-auto mb-2">
                      <table className="min-w-full text-sm border border-slate-700">{children}</table>
                    </div>
                  ),
                  thead: ({ children }) => <thead className="bg-slate-800">{children}</thead>,
                  tbody: ({ children }) => <tbody className="divide-y divide-slate-700">{children}</tbody>,
                  tr: ({ children }) => <tr>{children}</tr>,
                  th: ({ children }) => <th className="px-3 py-2 text-left text-slate-300 font-medium">{children}</th>,
                  td: ({ children }) => <td className="px-3 py-2 text-slate-200">{children}</td>,
                  // Style blockquotes
                  blockquote: ({ children }) => (
                    <blockquote className="border-l-4 border-slate-600 pl-4 italic text-slate-400 mb-2">{children}</blockquote>
                  ),
                  // Style horizontal rule
                  hr: () => <hr className="border-slate-700 my-4" />,
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          ) : message.isStreaming && !hasPendingToolCalls ? (
            <div className="flex items-center gap-2 text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">Thinking...</span>
            </div>
          ) : null}
        </div>

        {/* Timestamp */}
        <div className="mt-2 text-xs text-slate-500">
          {message.timestamp.toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
