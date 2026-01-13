# Chatbot Integration Guide for Frontend Developers

## Overview

This guide shows how to integrate the GreenLake AI Chatbot into your React application. The chatbot provides real-time streaming responses via WebSocket with features like:

- **JWT Authentication** with secure ticket-based WebSocket auth
- **Real-time Streaming** of AI responses with thinking indicators
- **User Confirmation** for write operations (updates, deletes, assignments)
- **Automatic Reconnection** with exponential backoff
- **Heartbeat Monitoring** to keep connections alive
- **Error Recovery** with graceful degradation

---

## Quick Start

### 1. Basic Integration

The simplest way to add chat to your app is using the `ChatWidget` component:

```tsx
import { ChatWidget } from '@/components/chat/ChatWidget'

export function MyPage() {
  return (
    <div>
      <h1>My Dashboard</h1>
      {/* Your content */}

      {/* Floating chat widget */}
      <ChatWidget
        apiBaseUrl="/api/agent"
        position="bottom-right"
      />
    </div>
  )
}
```

**That's it!** The widget handles connection, authentication, and UI automatically.

---

## Advanced Integration: Using the `useChat` Hook

For custom chat interfaces, use the `useChat` hook directly:

### Installation & Import

```tsx
import { useChat } from '@/hooks/useChat'
```

### Hook Initialization

```tsx
const {
  // State
  messages,           // Array of ChatMessage objects
  isConnected,        // WebSocket connection status
  isConnecting,       // Connection in progress
  isLoading,          // Waiting for AI response
  error,              // Error message (if any)
  conversationId,     // Current conversation ID
  pendingConfirmation, // Pending write operation (if any)

  // Actions
  connect,            // Manually connect WebSocket
  disconnect,         // Disconnect WebSocket
  sendMessage,        // Send a chat message
  confirmOperation,   // Confirm/cancel write operation
  cancel,             // Cancel current request
  clearConversation,  // Clear chat history
} = useChat({
  apiBaseUrl: '/api/agent',
  authToken: 'your-jwt-token',  // Optional: provide JWT directly
  getAuthToken: () => localStorage.getItem('jwt'), // Or: callback to get token
  autoReconnect: true, // Default: true (auto-reconnect on disconnect)
})
```

### Authentication Options

The hook supports three authentication modes:

1. **Direct Token** (recommended for production):
   ```tsx
   useChat({ authToken: 'eyJhbGciOiJIUzI1NiIs...' })
   ```

2. **Token Callback** (recommended for auth context integration):
   ```tsx
   const { getToken } = useAuth()
   useChat({ getAuthToken: () => getToken() })
   ```

3. **Development Mode** (no auth - uses dev-tenant/dev-user):
   ```tsx
   useChat({ /* no auth options */ })
   ```

---

## Message Types & Data Structures

### ChatMessage Type

```typescript
interface ChatMessage {
  id: string                    // Unique message ID
  role: 'user' | 'assistant' | 'tool'
  content: string               // Message text (markdown supported)
  thinking?: string             // AI's internal reasoning (optional)
  toolCalls?: ToolCall[]        // Tool invocations (optional)
  timestamp: Date               // Message timestamp
  isStreaming?: boolean         // True while response is streaming
}
```

### ToolCall Type

```typescript
interface ToolCall {
  id: string                    // Tool call ID
  name: string                  // Tool name (e.g., "search_devices")
  arguments: Record<string, unknown>  // Tool input parameters
  result?: unknown              // Tool result (present after completion)
}
```

### PendingConfirmation Type

```typescript
interface PendingConfirmation {
  operationId: string           // Operation ID to confirm/cancel
  message: string               // Human-readable confirmation prompt
  riskLevel: string             // 'low' | 'medium' | 'high'
}
```

---

## WebSocket Message Protocol

### Client → Server Messages

The `useChat` hook handles these automatically, but here's the protocol:

#### 1. Chat Message
```json
{
  "type": "chat",
  "message": "Find all switches in us-west",
  "conversation_id": "uuid-or-null"
}
```

#### 2. Confirmation Response
```json
{
  "type": "confirm",
  "operation_id": "op-12345",
  "confirmed": true  // or false to cancel
}
```

#### 3. Cancel Request
```json
{
  "type": "cancel"
}
```

#### 4. Heartbeat Ping
```json
{
  "type": "ping"
}
```

### Server → Client Events

The hook automatically processes these events and updates state:

#### 1. Text Delta (Streaming Response)
```json
{
  "type": "text_delta",
  "content": "I found 12 switches...",
  "sequence": 1
}
```

#### 2. Thinking Delta (AI Reasoning)
```json
{
  "type": "thinking_delta",
  "content": "Analyzing query parameters...",
  "sequence": 2
}
```

#### 3. Tool Call Start
```json
{
  "type": "tool_call_start",
  "tool_call_id": "call-abc123",
  "tool_name": "search_devices",
  "sequence": 3
}
```

#### 4. Tool Call End
```json
{
  "type": "tool_call_end",
  "tool_call_id": "call-abc123",
  "tool_arguments": {
    "query": "switches",
    "region": "us-west"
  },
  "sequence": 4
}
```

#### 5. Tool Result
```json
{
  "type": "tool_result",
  "tool_call_id": "call-abc123",
  "content": "[{\"id\": \"dev-123\", \"type\": \"switch\"}]",
  "sequence": 5
}
```

#### 6. Confirmation Required
```json
{
  "type": "confirmation_required",
  "content": "This will delete 5 devices. Confirm?",
  "metadata": {
    "operation_id": "op-12345",
    "risk_level": "high"
  },
  "sequence": 6
}
```

#### 7. Done (Response Complete)
```json
{
  "type": "done",
  "metadata": {
    "conversation_id": "uuid"
  },
  "sequence": 7
}
```

#### 8. Error
```json
{
  "type": "error",
  "content": "Database connection failed",
  "error_type": "fatal",  // or "recoverable"
  "sequence": 8
}
```

#### 9. Pong (Heartbeat Response)
```json
{
  "type": "pong"
}
```

---

## Confirmation Workflow for Write Operations

The chatbot requires **user confirmation** for destructive operations. Here's the flow:

### 1. User Requests Write Operation

```tsx
sendMessage("Delete device ABC-123")
```

### 2. Server Sends Confirmation Request

The hook sets `pendingConfirmation`:

```tsx
{
  operationId: "op-12345",
  message: "This will delete device ABC-123. Confirm?",
  riskLevel: "high"
}
```

### 3. Display Confirmation UI

```tsx
{pendingConfirmation && (
  <div className="confirmation-banner">
    <AlertTriangle className="icon" />
    <p>{pendingConfirmation.message}</p>
    <div className="buttons">
      <button onClick={() => confirmOperation(true)}>
        Confirm
      </button>
      <button onClick={() => confirmOperation(false)}>
        Cancel
      </button>
    </div>
  </div>
)}
```

### 4. User Confirms or Cancels

```tsx
// Confirm: executes the operation
confirmOperation(true)

// Cancel: aborts the operation
confirmOperation(false)
```

### Risk Levels

- **`low`**: Minor changes (e.g., update tag)
- **`medium`**: Significant changes (e.g., reassign device)
- **`high`**: Destructive operations (e.g., delete device)

Style your UI based on `pendingConfirmation.riskLevel`.

---

## Error Recovery

### Handling Connection Errors

The hook automatically handles connection failures:

```tsx
const { error, isConnected, connect } = useChat()

// Display error to user
{error && (
  <div className="error-banner">
    <AlertCircle className="icon" />
    <span>{error}</span>
    {!isConnected && (
      <button onClick={connect}>Reconnect</button>
    )}
  </div>
)}
```

### Error Types

1. **Connection Failed**: "WebSocket connection failed"
   - User should refresh or check network

2. **Not Connected**: "Not connected"
   - Call `connect()` to retry

3. **Connection Lost**: "Connection lost. Please refresh the page."
   - Max reconnection attempts exceeded (5 attempts)

4. **Server Errors**: Custom error messages from backend
   - Display to user and allow retry

---

## Reconnection Strategy

The hook implements **automatic reconnection** with exponential backoff:

### Configuration

```tsx
useChat({
  autoReconnect: true,  // Enable auto-reconnect (default)
})
```

### Reconnection Behavior

1. **Initial Delay**: 1 second
2. **Backoff Multiplier**: 2x (exponential)
3. **Max Delay**: 30 seconds
4. **Max Attempts**: 5

**Example Timeline:**
- Attempt 1: 1s delay
- Attempt 2: 2s delay
- Attempt 3: 4s delay
- Attempt 4: 8s delay
- Attempt 5: 16s delay
- After 5 failures: Give up, show error

### Heartbeat Monitoring

The hook sends **ping** every 30 seconds to keep the connection alive:

```tsx
// Automatically sent by the hook
{ "type": "ping" }

// Server responds with pong
{ "type": "pong" }
```

If pings fail, the connection is considered dead and reconnection starts.

### Manual Disconnect

Manual disconnects (e.g., user clicks "Close") **do not trigger auto-reconnect**:

```tsx
disconnect()  // No reconnection attempts
```

---

## Complete Integration Example

Here's a full custom chat component using the `useChat` hook:

```tsx
import { useState, useRef, useEffect } from 'react'
import { useChat } from '@/hooks/useChat'
import { Send, AlertTriangle, Check, XCircle, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

export function CustomChat() {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)

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
  } = useChat({
    apiBaseUrl: '/api/agent',
    getAuthToken: () => localStorage.getItem('jwt'),
  })

  // Connect on mount
  useEffect(() => {
    connect()
    return () => disconnect()
  }, [])

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (input.trim() && !isLoading) {
      sendMessage(input.trim())
      setInput('')
    }
  }

  return (
    <div className="chat-container">
      {/* Header */}
      <div className="chat-header">
        <h2>GreenLake Assistant</h2>
        <div className="status">
          {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
        </div>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message message-${msg.role}`}>
            <div className="message-content">
              <ReactMarkdown>{msg.content}</ReactMarkdown>
            </div>
            {msg.thinking && (
              <details className="message-thinking">
                <summary>Show reasoning</summary>
                <p>{msg.thinking}</p>
              </details>
            )}
            <div className="message-time">
              {msg.timestamp.toLocaleTimeString()}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Error Banner */}
      {error && (
        <div className="error-banner">
          <AlertTriangle />
          <span>{error}</span>
        </div>
      )}

      {/* Confirmation Dialog */}
      {pendingConfirmation && (
        <div className={`confirmation-banner risk-${pendingConfirmation.riskLevel}`}>
          <AlertTriangle />
          <p>{pendingConfirmation.message}</p>
          <div className="confirmation-buttons">
            <button
              onClick={() => confirmOperation(true)}
              className="btn-confirm"
            >
              <Check /> Confirm
            </button>
            <button
              onClick={() => confirmOperation(false)}
              className="btn-cancel"
            >
              <XCircle /> Cancel
            </button>
          </div>
        </div>
      )}

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="chat-input">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isConnected ? "Ask me anything..." : "Connecting..."}
          disabled={!isConnected || isLoading}
        />
        {isLoading ? (
          <button type="button" onClick={cancel} className="btn-cancel">
            <XCircle /> Cancel
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim() || !isConnected}
            className="btn-send"
          >
            <Send /> Send
          </button>
        )}
      </form>
    </div>
  )
}
```

### Example CSS

```css
.chat-container {
  display: flex;
  flex-direction: column;
  height: 600px;
  border: 1px solid #ccc;
  border-radius: 8px;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #ccc;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.message {
  margin-bottom: 16px;
  padding: 12px;
  border-radius: 8px;
}

.message-user {
  background: #e3f2fd;
  margin-left: 20%;
}

.message-assistant {
  background: #f5f5f5;
  margin-right: 20%;
}

.message-thinking {
  margin-top: 8px;
  font-size: 0.875rem;
  color: #666;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: #fee;
  border-top: 1px solid #fcc;
}

.confirmation-banner {
  padding: 16px;
  border-top: 1px solid #ccc;
}

.confirmation-banner.risk-high {
  background: #fff3cd;
  border-color: #ffc107;
}

.confirmation-buttons {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.chat-input {
  display: flex;
  gap: 8px;
  padding: 16px;
  border-top: 1px solid #ccc;
}

.chat-input input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.chat-input button {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.btn-send {
  background: #4caf50;
  color: white;
}

.btn-cancel {
  background: #f44336;
  color: white;
}
```

---

## Best Practices

### 1. **Always Connect on Mount**

```tsx
useEffect(() => {
  connect()
  return () => disconnect()
}, [])
```

### 2. **Handle Authentication Properly**

Use `getAuthToken` callback for auth context integration:

```tsx
const { getToken } = useAuth()
useChat({ getAuthToken: () => getToken() })
```

### 3. **Display Connection Status**

```tsx
{isConnected ? '🟢 Connected' : '🔴 Disconnected'}
```

### 4. **Show Loading States**

```tsx
{isLoading && <Loader2 className="animate-spin" />}
```

### 5. **Always Show Confirmations**

Never auto-confirm write operations:

```tsx
{pendingConfirmation && (
  <ConfirmationDialog
    onConfirm={() => confirmOperation(true)}
    onCancel={() => confirmOperation(false)}
  />
)}
```

### 6. **Render Markdown**

Use `react-markdown` for formatted AI responses:

```tsx
import ReactMarkdown from 'react-markdown'
<ReactMarkdown>{message.content}</ReactMarkdown>
```

### 7. **Auto-scroll to Bottom**

```tsx
const messagesEndRef = useRef<HTMLDivElement>(null)

useEffect(() => {
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
}, [messages])
```

### 8. **Disable Input When Disconnected**

```tsx
<input disabled={!isConnected || isLoading} />
```

### 9. **Clean Up on Unmount**

```tsx
useEffect(() => {
  connect()
  return () => disconnect()  // Important!
}, [])
```

### 10. **Handle Errors Gracefully**

```tsx
{error && (
  <div className="error">
    {error}
    {!isConnected && <button onClick={connect}>Retry</button>}
  </div>
)}
```

---

## Troubleshooting

### Connection Issues

**Problem**: "WebSocket connection failed"

**Solutions**:
1. Check that backend is running: `curl http://localhost:8000/api/agent/health`
2. Verify JWT token is valid (check browser console)
3. Check browser console for CORS errors
4. Ensure Redis is running (required for ticket auth)

### Authentication Errors

**Problem**: "Invalid or expired ticket" (WebSocket close code 4001)

**Solutions**:
1. Ensure JWT is provided via `authToken` or `getAuthToken`
2. Check JWT hasn't expired
3. Verify ticket endpoint is working: `POST /api/agent/ticket`

### Messages Not Appearing

**Problem**: Messages not displaying in UI

**Solutions**:
1. Check `messages` array in React DevTools
2. Verify `key` prop is unique for each message
3. Check for render errors in browser console

### Reconnection Not Working

**Problem**: Auto-reconnect not triggering

**Solutions**:
1. Ensure `autoReconnect: true` (default)
2. Check that disconnect wasn't manual (e.g., user clicked "Close")
3. Verify max attempts (5) not exceeded
4. Check browser console for errors

---

## API Reference

### Hook Options

```typescript
interface UseChatOptions {
  apiBaseUrl?: string           // Default: '/api/agent'
  authToken?: string            // JWT token for authentication
  getAuthToken?: () => string | null | Promise<string | null>
  autoReconnect?: boolean       // Default: true
}
```

### Hook Return Value

```typescript
interface UseChatReturn {
  // State
  messages: ChatMessage[]
  isConnected: boolean
  isConnecting: boolean
  isLoading: boolean
  error: string | null
  conversationId: string | null
  pendingConfirmation: PendingConfirmation | null

  // Actions
  connect: () => Promise<void>
  disconnect: () => void
  sendMessage: (message: string) => void
  confirmOperation: (confirmed: boolean) => void
  cancel: () => void
  clearConversation: () => void
}
```

---

## Security Considerations

### 1. **Never Pass JWT in WebSocket URL**

❌ **Bad**:
```tsx
const ws = new WebSocket(`ws://host/chat?token=${jwt}`)
```

✅ **Good** (our implementation):
```tsx
// 1. Exchange JWT for one-time ticket via REST
const { ticket } = await fetch('/api/agent/ticket', {
  headers: { Authorization: `Bearer ${jwt}` }
}).then(r => r.json())

// 2. Use ticket in WebSocket URL (consumed immediately)
const ws = new WebSocket(`ws://host/chat?ticket=${ticket}`)
```

### 2. **Ticket Properties**

- **One-time use**: Consumed on validation (prevents replay attacks)
- **Short-lived**: 60-second TTL (limits exposure window)
- **Bound to user**: Tied to tenant_id/user_id from JWT

### 3. **Always Require Confirmation for Writes**

Never auto-confirm destructive operations. Always show UI:

```tsx
{pendingConfirmation && <ConfirmDialog />}
```

---

## Additional Resources

- **WebSocket Authentication**: See `docs/websocket-authentication.md`
- **Backend API**: See `src/glp/agent/api/router.py`
- **Hook Implementation**: See `frontend/src/hooks/useChat.ts`
- **Example Component**: See `frontend/src/components/chat/ChatWidget.tsx`

---

## Summary

✅ **Use `ChatWidget`** for quick integration
✅ **Use `useChat` hook** for custom interfaces
✅ **Always authenticate** with JWT → ticket flow
✅ **Handle confirmations** for write operations
✅ **Show connection status** to users
✅ **Enable auto-reconnect** for resilience
✅ **Render markdown** for formatted responses
✅ **Clean up** on component unmount

Happy chatting! 🚀
