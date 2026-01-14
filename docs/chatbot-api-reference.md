# Chatbot API Reference

Complete API reference for the Agent Chatbot, including REST endpoints, WebSocket protocol, security features, and rate limiting.

## Table of Contents

- [Authentication](#authentication)
- [REST Endpoints](#rest-endpoints)
- [WebSocket Protocol](#websocket-protocol)
- [Request/Response Schemas](#requestresponse-schemas)
- [WebSocket Event Types](#websocket-event-types)
- [Security Features](#security-features)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)

---

## Authentication

The chatbot API uses a two-tier authentication system:

1. **REST Endpoints**: JWT Bearer token authentication
2. **WebSocket Connections**: Ticket-based authentication (derived from JWT)

### JWT Authentication (REST)

All REST endpoints require a valid JWT token in the Authorization header:

```http
Authorization: Bearer <jwt_token>
```

**JWT Claims Required:**
- `tenant_id` - Tenant identifier for multi-tenant isolation
- `user_id` - User identifier
- `session_id` - (Optional) Session identifier

### Ticket Authentication (WebSocket)

WebSocket connections use short-lived, one-time tickets instead of JWT tokens to avoid exposing secrets in URL query parameters.

**Security Principle:** Never pass JWT in WebSocket URL query params. Use tickets instead.

**Flow:**
1. Authenticate with JWT via REST endpoint
2. Call `POST /api/agent/ticket` to obtain a ticket
3. Use ticket to connect to WebSocket: `ws://host/api/agent/ws?ticket=XXX`

**Ticket Properties:**
- **One-time use**: Consumed on validation (atomic operation)
- **Short-lived**: 60 second TTL
- **Bound**: To user, tenant, and session from the JWT that created it
- **Secure**: 32-byte URL-safe random token

See [WebSocket Authentication Guide](./websocket-authentication.md) for detailed flow diagrams and security considerations.

---

## REST Endpoints

Base path: `/api/agent`

All endpoints require JWT authentication unless noted otherwise.

### POST /chat

Start a new chat message (non-streaming).

**Note:** For real-time streaming, use the [WebSocket endpoint](#websocket-ws) instead.

**Request:**
```json
{
  "message": "Find all switches in the us-west region",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000"  // Optional
}
```

**Response:** `200 OK`
```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing"
}
```

**Notes:**
- Creates a new conversation if `conversation_id` is null
- Processing happens asynchronously
- Client should connect via WebSocket to receive streaming events

---

### GET /conversations

List user's conversations with pagination.

**Query Parameters:**
- `limit` (integer, 1-100, default: 20) - Number of conversations to return
- `offset` (integer, ≥0, default: 0) - Offset for pagination

**Response:** `200 OK`
```json
{
  "conversations": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Device Query Discussion",
      "summary": "Searched for switches and updated tags",
      "message_count": 15,
      "last_message_preview": "I found 23 switches in us-west...",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T11:45:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

### GET /conversations/{conversation_id}

Get a single conversation with full message history.

**Path Parameters:**
- `conversation_id` (UUID) - Conversation identifier

**Response:** `200 OK`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Device Query Discussion",
  "summary": "Searched for switches and updated tags",
  "message_count": 15,
  "messages": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "role": "user",
      "content": "Find all switches in us-west",
      "thinking_summary": null,
      "tool_calls": null,
      "model_used": null,
      "tokens_used": null,
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440002",
      "role": "assistant",
      "content": "I found 23 switches in the us-west region...",
      "thinking_summary": "Query database for network devices [REDACTED]",
      "tool_calls": [
        {
          "id": "call_abc123",
          "name": "search_devices",
          "arguments": {"device_type": "switch", "region": "us-west"},
          "result": {"count": 23, "devices": [...]}
        }
      ],
      "model_used": "claude-3-5-sonnet-20241022",
      "tokens_used": 1250,
      "created_at": "2024-01-15T10:30:15Z"
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:45:00Z"
}
```

**Error Responses:**
- `404 Not Found` - Conversation not found or doesn't belong to user

---

### DELETE /conversations/{conversation_id}

Delete a conversation and all its messages.

**Path Parameters:**
- `conversation_id` (UUID) - Conversation identifier

**Response:** `204 No Content`

**Error Responses:**
- `404 Not Found` - Conversation not found or doesn't belong to user

---

### POST /confirm

Confirm or cancel a pending write operation.

**Note:** For WebSocket clients, use the `ws/confirm` message instead.

**Request:**
```json
{
  "operation_id": "770e8400-e29b-41d4-a716-446655440003",
  "confirmed": true
}
```

**Response:** `200 OK`
```json
{
  "status": "confirmed",
  "events": [
    {
      "type": "text_delta",
      "content": "Executing operation...",
      "sequence": 1,
      "timestamp": "2024-01-15T10:30:00Z"
    },
    {
      "type": "done",
      "sequence": 2,
      "timestamp": "2024-01-15T10:30:05Z"
    }
  ]
}
```

**Error Responses:**
- `404 Not Found` - Pending operation not found

---

### POST /ticket

Get a one-time ticket for WebSocket connection.

**Request:** Empty body (ticket generated from JWT auth context)

**Response:** `200 OK`
```json
{
  "ticket": "abc123def456...",
  "expires_in": 60
}
```

**Notes:**
- Ticket is valid for 60 seconds
- Ticket can only be used once
- Ticket is bound to user/tenant/session from the JWT

**Error Responses:**
- `503 Service Unavailable` - Ticket auth not configured

---

### GET /memory/stats

Get memory statistics for the current user.

**Response:** `200 OK`
```json
{
  "total": 150,
  "active": 120,
  "by_type": {
    "entity": {
      "count": 50,
      "avg_confidence": 0.85
    },
    "preference": {
      "count": 30,
      "avg_confidence": 0.92
    },
    "fact": {
      "count": 40,
      "avg_confidence": 0.78
    }
  }
}
```

**Notes:**
- Returns statistics about semantic memory for the user
- Used for debugging and monitoring memory performance

---

## WebSocket Protocol

### WebSocket: /ws

Real-time bidirectional communication for chat streaming.

**Connection URL:**
```
ws://host/api/agent/ws?ticket=<one-time-ticket>
```

**Connection Flow:**
1. Client authenticates with JWT and calls `POST /api/agent/ticket`
2. Client connects to WebSocket with ticket in query param
3. Server validates and consumes ticket (one-time use, atomic operation)
4. Connection established - client can send messages
5. Server streams events back to client

**Security:**
- Ticket is REQUIRED (no header fallback for security)
- Ticket is one-time use and expires in 60 seconds
- Ticket is bound to tenant/user/session from the JWT that created it

### Client → Server Messages

#### Chat Message
```json
{
  "type": "chat",
  "message": "Find all switches in us-west region",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000"  // Optional
}
```

**Fields:**
- `type` - Always "chat"
- `message` (string, 1-10000 chars) - User message
- `conversation_id` (UUID, optional) - Resume existing conversation or null for new

#### Confirmation Response
```json
{
  "type": "confirm",
  "operation_id": "770e8400-e29b-41d4-a716-446655440003",
  "confirmed": true
}
```

**Fields:**
- `type` - Always "confirm"
- `operation_id` (UUID) - ID of pending operation from `confirmation_required` event
- `confirmed` (boolean) - true to proceed, false to cancel

#### Cancel Operation
```json
{
  "type": "cancel"
}
```

**Fields:**
- `type` - Always "cancel"

**Effect:** Cancels the current streaming operation

#### Heartbeat
```json
{
  "type": "ping"
}
```

**Response:**
```json
{
  "type": "pong"
}
```

**Purpose:** Keep connection alive, detect disconnections

### Server → Client Events

See [WebSocket Event Types](#websocket-event-types) section below for complete event reference.

### Connection Close Codes

- `4001` - Invalid or expired ticket
- `4003` - Ticket auth not configured
- `1000` - Normal closure
- `1011` - Internal server error

---

## Request/Response Schemas

### ChatRequest

Request to send a chat message.

**Schema:**
```typescript
{
  message: string;        // 1-10000 characters
  conversation_id?: UUID; // Optional, null for new conversation
}
```

**Example:**
```json
{
  "message": "Find all switches in the us-west region",
  "conversation_id": null
}
```

### ChatResponse

Response after initiating a chat.

**Schema:**
```typescript
{
  conversation_id: UUID;
  status: string;  // "processing"
}
```

**Example:**
```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing"
}
```

### MessageResponse

A message in a conversation.

**Schema:**
```typescript
{
  id: UUID;
  role: string;                    // "user" | "assistant"
  content: string;
  thinking_summary?: string;       // Redacted CoT summary (assistant only)
  tool_calls?: Array<{             // Tool executions (assistant only)
    id: string;
    name: string;
    arguments: object;
    result: any;
  }>;
  model_used?: string;             // e.g., "claude-3-5-sonnet-20241022"
  tokens_used?: number;
  created_at: string;              // ISO 8601 timestamp
}
```

### ConversationResponse

Full conversation with messages.

**Schema:**
```typescript
{
  id: UUID;
  title?: string;
  summary?: string;
  message_count: number;
  messages: MessageResponse[];
  created_at: string;
  updated_at: string;
}
```

### ConversationListItem

Summary of a conversation for listing.

**Schema:**
```typescript
{
  id: UUID;
  title?: string;
  summary?: string;
  message_count: number;
  last_message_preview?: string;
  created_at: string;
  updated_at: string;
}
```

### ConversationListResponse

Paginated list of conversations.

**Schema:**
```typescript
{
  conversations: ConversationListItem[];
  total: number;
  limit: number;
  offset: number;
}
```

### ConfirmationRequest

Request to confirm or cancel a pending operation.

**Schema:**
```typescript
{
  operation_id: UUID;
  confirmed: boolean;
}
```

**Example:**
```json
{
  "operation_id": "770e8400-e29b-41d4-a716-446655440003",
  "confirmed": true
}
```

### TicketResponse

Response with WebSocket connection ticket.

**Schema:**
```typescript
{
  ticket: string;      // URL-safe random token
  expires_in: number;  // Seconds until expiration (60)
}
```

**Example:**
```json
{
  "ticket": "abc123def456...",
  "expires_in": 60
}
```

### MemoryStatsResponse

Memory statistics for a user.

**Schema:**
```typescript
{
  total: number;
  active: number;
  by_type: {
    [type: string]: {
      count: number;
      avg_confidence: number;
      [key: string]: any;
    }
  }
}
```

---

## WebSocket Event Types

All events sent from server to client follow this base schema:

```typescript
{
  type: string;
  sequence: number;            // Monotonic sequence number
  correlation_id?: string;     // Optional correlation ID
  timestamp: string;           // ISO 8601 timestamp

  // Event-specific fields
  content?: string;
  tool_call_id?: string;
  tool_name?: string;
  tool_arguments?: object;
  error_type?: string;
  metadata?: object;
}
```

### Event Types

#### text_delta

Streaming text chunk from assistant response.

**Fields:**
- `content` (string) - Text chunk to append

**Example:**
```json
{
  "type": "text_delta",
  "sequence": 1,
  "content": "I found 23 switches in the us-west region",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### thinking_delta

Streaming chunk from chain-of-thought reasoning (if enabled).

**Fields:**
- `content` (string) - Thinking chunk

**Security Note:** Raw thinking is never stored, only redacted summaries.

**Example:**
```json
{
  "type": "thinking_delta",
  "sequence": 2,
  "content": "I need to query the devices table for switches...",
  "timestamp": "2024-01-15T10:30:01Z"
}
```

#### tool_call_start

Assistant is calling a tool.

**Fields:**
- `tool_call_id` (string) - Unique tool call identifier
- `tool_name` (string) - Name of the tool being called
- `tool_arguments` (object) - Arguments passed to the tool

**Example:**
```json
{
  "type": "tool_call_start",
  "sequence": 3,
  "tool_call_id": "call_abc123",
  "tool_name": "search_devices",
  "tool_arguments": {
    "device_type": "switch",
    "region": "us-west"
  },
  "timestamp": "2024-01-15T10:30:02Z"
}
```

#### tool_call_result

Result from a tool execution.

**Fields:**
- `tool_call_id` (string) - Matches the tool_call_start ID
- `content` (string) - Serialized result
- `metadata` (object, optional) - Additional metadata

**Example:**
```json
{
  "type": "tool_call_result",
  "sequence": 4,
  "tool_call_id": "call_abc123",
  "content": "{\"count\": 23, \"devices\": [...]}",
  "metadata": {
    "execution_time_ms": 150,
    "cache_hit": false
  },
  "timestamp": "2024-01-15T10:30:03Z"
}
```

#### confirmation_required

Write operation requires user confirmation.

**Fields:**
- `content` (string) - Confirmation message to display
- `metadata` (object) - Contains operation details

**Metadata Fields:**
- `operation_id` (UUID) - ID to use in confirmation response
- `operation_type` (string) - Type of operation (e.g., "archive_devices")
- `risk_level` (string) - "low" | "medium" | "high" | "critical"
- `device_count` (number, optional) - Number of devices affected

**Example:**
```json
{
  "type": "confirmation_required",
  "sequence": 5,
  "content": "Are you sure you want to archive 10 devices? Archived devices will no longer receive updates.",
  "metadata": {
    "operation_id": "770e8400-e29b-41d4-a716-446655440003",
    "operation_type": "archive_devices",
    "risk_level": "high",
    "device_count": 10
  },
  "timestamp": "2024-01-15T10:30:04Z"
}
```

**Response Required:** Client must send a `confirm` message with the operation_id and confirmed=true/false.

#### done

Stream completed successfully.

**Fields:**
- `metadata` (object, optional) - Summary metadata

**Metadata Fields:**
- `message_id` (UUID, optional) - ID of the saved message
- `tokens_used` (number, optional) - Total tokens consumed
- `model_used` (string, optional) - Model identifier

**Example:**
```json
{
  "type": "done",
  "sequence": 6,
  "metadata": {
    "message_id": "660e8400-e29b-41d4-a716-446655440002",
    "tokens_used": 1250,
    "model_used": "claude-3-5-sonnet-20241022"
  },
  "timestamp": "2024-01-15T10:30:05Z"
}
```

#### error

An error occurred during processing.

**Fields:**
- `content` (string) - Error message
- `error_type` (string) - Error classification

**Error Types:**
- `fatal` - Unrecoverable error, stream terminated
- `tool_error` - Tool execution failed, processing may continue
- `rate_limit` - Rate limit exceeded
- `quota_exceeded` - Tenant quota exceeded
- `validation` - Invalid input
- `auth` - Authentication/authorization error

**Example:**
```json
{
  "type": "error",
  "sequence": 7,
  "content": "Daily operation quota exceeded for tenant. Used 100/100 operations. Resets at 2024-01-16 00:00:00 UTC (next day).",
  "error_type": "quota_exceeded",
  "timestamp": "2024-01-15T10:30:06Z"
}
```

#### cancelled

Operation was cancelled by user.

**Fields:**
- `content` (string) - Cancellation message

**Example:**
```json
{
  "type": "cancelled",
  "sequence": 8,
  "content": "Operation cancelled",
  "timestamp": "2024-01-15T10:30:07Z"
}
```

#### pong

Response to ping heartbeat.

**Example:**
```json
{
  "type": "pong",
  "sequence": 9,
  "timestamp": "2024-01-15T10:30:08Z"
}
```

---

## Security Features

### Chain-of-Thought (CoT) Redaction

**Security Principle:** Never store raw CoT - only redacted summaries.

The chatbot uses Claude's extended thinking feature for complex reasoning. However, thinking content may contain sensitive information from tool results (API keys, IP addresses, credentials, etc.).

**Protection:**
- Raw thinking is **never** stored in the database
- Thinking is redacted in real-time before storage
- Only redacted summaries are persisted in `thinking_summary` field
- 20+ patterns detected and redacted (see below)

**Redacted Patterns:**
- Authentication tokens (Bearer tokens, API keys, access tokens)
- Passwords and secrets
- Database connection strings (PostgreSQL, MySQL, MongoDB, Redis)
- AWS credentials
- IP addresses (IPv4)
- MAC addresses
- JWT tokens
- Long base64 strings (likely secrets)
- SSH private keys
- Generic hex strings (32+ chars)

**Example:**
```
Original: "Found device at 192.168.1.100 with API key sk_live_abc123def456"
Redacted: "Found device at [IP_ADDRESS] with API key [BASE64_REDACTED]"
```

**Implementation:** See `src/glp/agent/security/cot_redactor.py`

### Multi-Tenant Isolation

All queries and operations are automatically scoped to the authenticated tenant.

**Enforcement:**
1. JWT validation extracts `tenant_id`
2. `UserContext` passed to all operations
3. Database queries filter by `tenant_id`
4. Cross-tenant access is impossible

**Example:**
```python
# All database queries are scoped
conversations = await db.list_conversations(
    tenant_id=context.tenant_id,  # Always required
    user_id=context.user_id,
    limit=20
)
```

### Ticket Security

WebSocket tickets use multiple security layers:

**Generation:**
- 32-byte cryptographically secure random token (`secrets.token_urlsafe`)
- Bound to user, tenant, session from JWT
- Stored in Redis with 60-second TTL

**Validation:**
- Atomic get-and-delete operation (prevents race conditions)
- One-time use (consumed on validation)
- Constant-time comparison (`secrets.compare_digest`)
- Clock skew tolerance (max 120 seconds)

**Atomicity:**
```lua
-- Lua script ensures atomic get+delete (no race conditions)
local value = redis.call('GET', KEYS[1])
if value then
    redis.call('DEL', KEYS[1])
end
return value
```

**Why not JWT in WebSocket query params?**
- Query params are logged by proxies, load balancers, and browsers
- URL history exposes secrets
- Tickets are short-lived and single-use, minimizing exposure

### Write Operation Confirmation

Dangerous write operations require explicit user confirmation.

**Risk Assessment:**
- **LOW**: Add device, update tags (no confirmation)
- **MEDIUM**: Assign application, assign subscription (confirmation for 5+ devices)
- **HIGH**: Archive devices, unassign subscription (always confirm)
- **CRITICAL**: Bulk operations (20+ devices, multi-step confirmation)

**Flow:**
1. Agent calls write tool (e.g., archive_devices)
2. System assesses risk based on operation type and device count
3. If confirmation required, sends `confirmation_required` event
4. User confirms/cancels via UI
5. Client sends `confirm` message
6. System executes or cancels operation

**Example:**
```json
// Server sends:
{
  "type": "confirmation_required",
  "content": "Are you sure you want to archive 10 devices?",
  "metadata": {
    "operation_id": "770e8400-...",
    "risk_level": "high"
  }
}

// Client responds:
{
  "type": "confirm",
  "operation_id": "770e8400-...",
  "confirmed": true
}
```

### Audit Logging

All write operations are logged for compliance and debugging.

**Logged Events:**
- `write_operation_start` - Before execution
- `write_operation_success` - After successful execution
- `write_operation_failed` - After failure

**Log Fields:**
- `tenant_id` - For isolation
- `user_id` - Who performed the action
- `operation_type` - What was done
- `arguments` - Operation details
- `risk_level` - Assessed risk
- `result` - Outcome (truncated)

---

## Rate Limiting

### Per-Tenant Daily Quotas

Write operations are rate-limited per tenant to prevent abuse.

**Default Limits:**
- **100 operations per day** per tenant
- **Resets at midnight UTC**

**Quota Enforcement:**
- Tracked in Redis (persists across restarts)
- Atomic increment operations (no race conditions)
- Keys automatically expire at end of day

**Environment Variables:**
```bash
TENANT_DAILY_QUOTA=100  # Override default daily quota
```

**Quota Exceeded Response:**
```json
{
  "type": "error",
  "content": "Daily operation quota exceeded for tenant. Used 100/100 operations. Resets at 2024-01-16 00:00:00 UTC (next day).",
  "error_type": "quota_exceeded"
}
```

**HTTP Status:** `429 Too Many Requests` (REST endpoints)

### Tiered Device Limits

Operations are limited by the number of devices they affect, based on risk level.

**Limits by Risk Level:**
- **LOW** (add device, update tags): 50 devices max
- **MEDIUM** (assign app, assign subscription): 25 devices max
- **HIGH** (archive, unassign subscription): 10 devices max
- **CRITICAL** (bulk operations): 5 devices max

**Environment Variables:**
```bash
MAX_DEVICES_LOW_RISK=50
MAX_DEVICES_MEDIUM_RISK=25
MAX_DEVICES_HIGH_RISK=10
MAX_DEVICES_CRITICAL_RISK=5
```

**Limit Exceeded Response:**
```json
{
  "type": "error",
  "content": "Operation 'archive_devices' exceeds maximum device limit. Got 15 devices, maximum is 10. Please split into smaller batches of 10 or fewer.",
  "error_type": "validation"
}
```

**HTTP Status:** `400 Bad Request` (REST endpoints)

### Redis-Backed Persistence

Quotas persist across server restarts using Redis.

**Redis Keys:**
```
quota:{tenant_id}:ops:{YYYY-MM-DD}      - Operations count
quota:{tenant_id}:devices:{YYYY-MM-DD}  - Devices count
```

**Expiration:** Keys expire at end of day (UTC)

**Fallback:** If Redis is unavailable, falls back to in-memory tracking (lost on restart)

---

## Error Handling

### Error Response Format

REST endpoints return errors in this format:

```json
{
  "detail": "Error message here"
}
```

**Common HTTP Status Codes:**
- `400 Bad Request` - Invalid input, device limit exceeded
- `401 Unauthorized` - Invalid or missing JWT
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `429 Too Many Requests` - Quota exceeded
- `503 Service Unavailable` - Agent not initialized, ticket auth not configured

### WebSocket Error Events

WebSocket errors are sent as events:

```json
{
  "type": "error",
  "content": "Error message",
  "error_type": "fatal | tool_error | rate_limit | quota_exceeded | validation | auth"
}
```

### Recoverable vs Fatal Errors

**Recoverable Errors:**
- Tool execution failures (e.g., device not found)
- Validation errors (e.g., invalid device ID format)
- Rate limit errors (retry later)

**Fatal Errors:**
- Authentication failures
- Agent not initialized
- Unhandled exceptions

**Handling:**
- **Recoverable**: Agent may retry or ask user for correction
- **Fatal**: Stream terminates, client should disconnect and alert user

### Retry Strategy

**For Rate Limits:**
- Wait until quota resets (midnight UTC)
- Split large operations into smaller batches

**For Tool Errors:**
- Agent may automatically retry with different parameters
- Agent may ask user for clarification

**For Network Errors:**
- Client should implement exponential backoff
- Reconnect with new ticket

---

## Complete Example Flow

### 1. Authenticate and Get Ticket

```javascript
// Authenticate with JWT
const response = await fetch('/api/agent/ticket', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${jwtToken}`,
    'Content-Type': 'application/json'
  }
});

const { ticket } = await response.json();
// ticket: "abc123def456...", expires_in: 60
```

### 2. Connect WebSocket

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/agent/ws?ticket=${ticket}`);

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  handleEvent(message);
};
```

### 3. Send Chat Message

```javascript
ws.send(JSON.stringify({
  type: 'chat',
  message: 'Find all switches in us-west region',
  conversation_id: null  // New conversation
}));
```

### 4. Handle Streaming Events

```javascript
function handleEvent(event) {
  switch (event.type) {
    case 'text_delta':
      appendText(event.content);
      break;

    case 'tool_call_start':
      showToolIndicator(event.tool_name);
      break;

    case 'tool_call_result':
      hideToolIndicator();
      break;

    case 'confirmation_required':
      showConfirmDialog(event.content, event.metadata.operation_id);
      break;

    case 'done':
      markComplete(event.metadata);
      break;

    case 'error':
      showError(event.content, event.error_type);
      break;
  }
}
```

### 5. Confirm Write Operation

```javascript
function confirmOperation(operationId, confirmed) {
  ws.send(JSON.stringify({
    type: 'confirm',
    operation_id: operationId,
    confirmed: confirmed
  }));
}
```

### 6. Heartbeat (Keep-Alive)

```javascript
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  }
}, 30000);  // Ping every 30 seconds
```

---

## Related Documentation

- [WebSocket Authentication Guide](./websocket-authentication.md) - Detailed ticket auth flow and security
- [Chatbot Integration Guide](./chatbot-integration-guide.md) - Step-by-step integration tutorial
- API Implementation: `src/glp/agent/api/router.py`
- Security Implementation: `src/glp/agent/security/`

---

## Environment Variables Reference

```bash
# JWT Authentication
JWT_SECRET=your-secret-key-here

# LLM Providers
ANTHROPIC_API_KEY=sk-ant-...           # Primary (Claude)
OPENAI_API_KEY=sk-...                  # Fallback + embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-3-large

# Redis (for tickets and quotas)
REDIS_URL=redis://localhost:6379

# Rate Limiting
TENANT_DAILY_QUOTA=100                 # Operations per day per tenant
MAX_DEVICES_LOW_RISK=50
MAX_DEVICES_MEDIUM_RISK=25
MAX_DEVICES_HIGH_RISK=10
MAX_DEVICES_CRITICAL_RISK=5
```

---

**Version:** 1.0
**Last Updated:** 2024-01-15
