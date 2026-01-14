# WebSocket Authentication Flow

This document describes the secure authentication flow for WebSocket connections in the HPE GreenLake Agent Chatbot.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [JWT Authentication](#jwt-authentication)
- [Ticket Request Flow](#ticket-request-flow)
- [WebSocket Connection](#websocket-connection)
- [Security Guarantees](#security-guarantees)
- [Implementation Examples](#implementation-examples)
- [Error Handling](#error-handling)
- [Configuration](#configuration)

## Overview

The WebSocket authentication system uses a two-phase approach to ensure secure real-time communication:

1. **Phase 1: JWT Authentication** - Client authenticates with the REST API using a JWT token
2. **Phase 2: Ticket Exchange** - Client exchanges the JWT for a short-lived, one-time-use WebSocket ticket
3. **Phase 3: WebSocket Connection** - Client connects to WebSocket using the ticket

**Security Principle:** Never pass JWT tokens in WebSocket URL query parameters. Instead, use short-lived tickets that are consumed immediately upon validation.

## Architecture

```
┌─────────────┐                         ┌──────────────────┐
│             │  1. POST /api/agent/    │                  │
│   Client    │     ticket              │   API Server     │
│             │     Authorization:      │   (FastAPI)      │
│  (Browser)  │     Bearer <JWT>        │                  │
│             │ ───────────────────────>│                  │
│             │                         │                  │
│             │  2. Response            │                  │
│             │     {ticket: "abc123",  │                  │
│             │      expires_in: 60}    │                  │
│             │<─────────────────────── │                  │
│             │                         │                  │
│             │                         └──────────────────┘
│             │                                  │
│             │                                  │ Store ticket
│             │                                  ▼
│             │                         ┌──────────────────┐
│             │  3. Connect WebSocket   │                  │
│             │     ws://host/api/      │     Redis        │
│             │     agent/ws?ticket=... │                  │
│             │ ───────────────────────>│  ws_ticket:abc   │
│             │                         │  {user_id, ...}  │
│             │  4. Validate & consume  │  TTL: 60s        │
│             │     ticket (one-time)   │                  │
│             │<─────────────────────── │                  │
│             │                         └──────────────────┘
│             │  5. Streaming events
│             │     {type: "text_delta",
│             │      content: "..."}
│             │<───────────────────────
└─────────────┘
```

## JWT Authentication

### Overview

All REST API endpoints require JWT authentication. The JWT contains:

- **User ID** (`sub` claim) - Identifies the user
- **Tenant ID** (`tenant_id` claim) - Isolates data by tenant
- **Session ID** (`session_id` claim) - Tracks user sessions
- **Standard claims** (`exp`, `iat`, `nbf`, `iss`, `aud`) - Security validation

### Supported Algorithms

The system supports both symmetric and asymmetric JWT algorithms:

**Symmetric (HMAC):**
- HS256, HS384, HS512 - Shared secret required

**Asymmetric (RSA/ECDSA):**
- RS256, RS384, RS512 - RSA with SHA-2
- ES256, ES384, ES512 - ECDSA with SHA-2
- PS256, PS384, PS512 - RSA-PSS with SHA-2

### Security Features

1. **Algorithm Allowlist** - Only cryptographically secure algorithms are permitted
2. **'none' Algorithm Rejection** - Explicitly blocks CVE-2015-2951 vulnerability
3. **Claim Validation** - Full validation of exp, nbf, iat, iss, aud claims
4. **Clock Skew Tolerance** - Configurable tolerance (default: 30 seconds)
5. **Comprehensive Logging** - All authentication failures are logged

### JWT Validation Flow

```python
# In src/glp/agent/api/auth.py

async def validate_jwt_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> TokenPayload:
    """
    1. Extract Bearer token from Authorization header
    2. Validate algorithm is in allowlist
    3. Decode and verify signature
    4. Validate claims (exp, nbf, iss, aud)
    5. Extract tenant_id, user_id, session_id
    6. Return validated payload
    """
```

### Usage in Endpoints

All agent endpoints use the `get_user_context` dependency:

```python
@router.post("/ticket")
async def get_websocket_ticket(
    context: UserContext = Depends(get_user_context),
) -> TicketResponse:
    """Endpoint automatically validates JWT and extracts user context."""
```

## Ticket Request Flow

### Step 1: Client Requests Ticket

The client makes an authenticated POST request to `/api/agent/ticket`:

**Request:**
```http
POST /api/agent/ticket HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Content-Type: application/json
```

**Response:**
```json
{
  "ticket": "xQr8zN2mK5vL9pJ4hF3wG7sD6aT1bY0cX...",
  "expires_in": 60
}
```

### Step 2: Server Creates Ticket

The server performs the following steps:

1. **Validates JWT** - Extracts user context from validated token
2. **Generates Ticket** - Creates cryptographically secure random ticket (32 bytes, URL-safe)
3. **Stores in Redis** - Stores ticket data with TTL (default: 60 seconds)
4. **Returns Ticket** - Sends ticket to client

**Ticket Data Structure:**

```python
@dataclass
class WebSocketTicket:
    ticket: str              # The ticket string (secret)
    user_id: str            # User identifier from JWT
    tenant_id: str          # Tenant identifier from JWT
    session_id: str         # Session identifier from JWT
    conversation_id: Optional[str]  # Optional conversation to reconnect to
    created_at: float       # Creation timestamp (for clock skew validation)
```

**Redis Storage:**

```
Key:   ws_ticket:xQr8zN2mK5vL9pJ4hF3wG7sD6aT1bY0cX...
Value: {"ticket": "xQr8...", "user_id": "user123", "tenant_id": "tenant456", ...}
TTL:   60 seconds
```

### Implementation

```python
# In src/glp/agent/api/router.py

@router.post("/ticket", response_model=TicketResponse)
async def get_websocket_ticket(
    context: UserContext = Depends(get_user_context),
) -> TicketResponse:
    """Get a one-time ticket for WebSocket connection."""

    if not _deps.ticket_auth:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ticket auth not configured",
        )

    ticket = await _deps.ticket_auth.create_ticket(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        session_id=context.session_id or "default",
    )

    return TicketResponse(
        ticket=ticket,
        expires_in=60,
    )
```

## WebSocket Connection

### Step 1: Client Connects with Ticket

The client connects to the WebSocket endpoint with the ticket as a query parameter:

```
ws://api.example.com/api/agent/ws?ticket=xQr8zN2mK5vL9pJ4hF3wG7sD6aT1bY0cX...
```

**Important:** The ticket is passed as a query parameter (not in headers) because WebSocket connections cannot include custom headers in browser environments.

### Step 2: Server Validates and Consumes Ticket

The server performs atomic ticket validation:

1. **Atomic Get-and-Delete** - Retrieves and deletes ticket in a single operation
2. **Validates Ticket** - Checks ticket format, expiration, and user/tenant binding
3. **Extracts Context** - Converts ticket data to UserContext
4. **Accepts Connection** - Establishes WebSocket connection

**Critical: Atomic Operations**

The system uses atomic operations to prevent race conditions:

```python
# Strategy 1: GETDEL (Redis 6.2+)
data = await redis.getdel(f"ws_ticket:{ticket}")

# Strategy 2: Lua script (Redis 2.6+) - fallback
ATOMIC_GETDEL_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if value then
    redis.call('DEL', KEYS[1])
end
return value
"""
data = await redis.eval(ATOMIC_GETDEL_SCRIPT, 1, key)
```

**Why Atomic Operations?**

Non-atomic operations could allow two concurrent requests to both validate the same ticket, violating the one-time-use guarantee. The system uses GETDEL or Lua scripts to ensure atomicity.

### Step 3: Message Exchange

Once connected, the client and server exchange JSON messages:

**Client → Server Messages:**

```json
// Chat message
{
  "type": "chat",
  "message": "Show me active devices",
  "conversation_id": "uuid-optional"
}

// Confirmation
{
  "type": "confirm",
  "operation_id": "op-123",
  "confirmed": true
}

// Cancel operation
{
  "type": "cancel"
}

// Heartbeat (keep-alive)
{
  "type": "ping"
}
```

**Server → Client Events:**

```json
// Text streaming
{
  "type": "text_delta",
  "content": "Here are the active devices...",
  "sequence": 1
}

// Thinking process (chain-of-thought)
{
  "type": "thinking_delta",
  "content": "I need to query the database...",
  "sequence": 2
}

// Tool call start
{
  "type": "tool_call_start",
  "tool_call_id": "call-1",
  "tool_name": "search_devices",
  "sequence": 3
}

// Tool result
{
  "type": "tool_result",
  "tool_call_id": "call-1",
  "content": "Found 42 devices",
  "sequence": 4
}

// Confirmation required (for write operations)
{
  "type": "confirmation_required",
  "content": "This will delete 5 devices. Confirm?",
  "metadata": {
    "operation_id": "op-123",
    "risk_level": "high"
  },
  "sequence": 5
}

// Completion
{
  "type": "done",
  "metadata": {
    "conversation_id": "uuid",
    "message_count": 10
  },
  "sequence": 6
}

// Error
{
  "type": "error",
  "content": "Database connection failed",
  "error_type": "fatal",
  "sequence": 7
}

// Heartbeat response
{
  "type": "pong"
}
```

### Implementation

```python
# In src/glp/agent/api/router.py

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: str = Query(..., description="One-time authentication ticket"),
):
    """WebSocket endpoint for streaming chat."""

    # Validate and consume ticket (one-time use)
    ticket_data = await _deps.ticket_auth.validate_ticket(ticket)
    if not ticket_data:
        await websocket.close(code=4001, reason="Invalid or expired ticket")
        return

    # Convert ticket data to UserContext
    context = UserContext(
        tenant_id=ticket_data.tenant_id,
        user_id=ticket_data.user_id,
        session_id=ticket_data.session_id,
    )

    # Accept connection
    await websocket.accept()

    # Stream events
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "chat":
                async for event in orchestrator.chat(data["message"], context):
                    await websocket.send_json(event.to_dict())
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={context.user_id}")
```

## Security Guarantees

### 1. One-Time Use

**Guarantee:** Each ticket can only be used once.

**Implementation:**
- Atomic GETDEL or Lua script ensures ticket is deleted on first validation
- Second validation attempt will find no ticket and fail
- Prevents replay attacks and concurrent connections with same ticket

**Attack Prevention:**
- ✅ Prevents ticket replay
- ✅ Prevents concurrent connections
- ✅ Prevents race conditions

### 2. Short Time-to-Live (TTL)

**Guarantee:** Tickets expire after 60 seconds.

**Implementation:**
- Redis SETEX with 60-second TTL
- Server validates `created_at` timestamp with 120-second max age (clock skew tolerance)
- Expired tickets are automatically purged by Redis

**Attack Prevention:**
- ✅ Limits window for ticket theft
- ✅ Limits window for brute force attacks
- ✅ Automatic cleanup of unused tickets

### 3. Tenant Isolation

**Guarantee:** Users can only access data from their own tenant.

**Implementation:**
- Ticket contains `tenant_id` from validated JWT
- All database queries filter by tenant_id
- Cross-tenant access is impossible

**Attack Prevention:**
- ✅ Prevents cross-tenant data access
- ✅ Ensures multi-tenant isolation
- ✅ Enforces tenant boundaries at all layers

### 4. No JWT in URL

**Guarantee:** JWT tokens never appear in WebSocket URLs or logs.

**Implementation:**
- JWT is only used in REST API Authorization headers
- WebSocket URLs only contain short-lived tickets
- Tickets are useless after consumption

**Attack Prevention:**
- ✅ Prevents JWT leakage in server logs
- ✅ Prevents JWT leakage in browser history
- ✅ Prevents JWT leakage in referrer headers
- ✅ Limits impact of URL interception

### 5. Cryptographically Secure Tickets

**Guarantee:** Tickets are unpredictable and cannot be guessed.

**Implementation:**
- Uses `secrets.token_urlsafe(32)` - 32 bytes of cryptographic randomness
- 256 bits of entropy (2^256 possibilities)
- URL-safe Base64 encoding

**Attack Prevention:**
- ✅ Prevents ticket guessing
- ✅ Prevents brute force attacks
- ✅ Ensures collision resistance

### 6. Clock Skew Tolerance

**Guarantee:** System tolerates reasonable clock differences between servers.

**Implementation:**
- JWT validation: 30-second clock skew (configurable)
- Ticket validation: 120-second max age (60s TTL + 60s tolerance)
- Prevents false rejections due to time drift

**Attack Prevention:**
- ✅ Handles distributed system clock drift
- ✅ Prevents false positive security alerts
- ✅ Maintains security while improving reliability

## Implementation Examples

### Backend: Creating Ticket Auth Service

```python
# In src/glp/assignment/app.py (or your FastAPI app)

import redis.asyncio as redis
from src.glp.agent.security.ticket_auth import WebSocketTicketAuth
from src.glp.agent.api.router import create_agent_dependencies

# Create Redis client
redis_client = redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True,
)

# Create ticket auth service
ticket_auth = WebSocketTicketAuth(
    redis=redis_client,
    ttl=60,  # 60 second TTL
)

# Initialize agent dependencies
create_agent_dependencies(
    orchestrator=agent_orchestrator,
    ticket_auth=ticket_auth,
)

# Include agent router
app.include_router(agent_router)
```

### Backend: Ticket Creation

```python
# In src/glp/agent/security/ticket_auth.py

class WebSocketTicketAuth:
    """WebSocket ticket authentication service."""

    async def create_ticket(
        self,
        user_id: str,
        tenant_id: str,
        session_id: str,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Create a new WebSocket authentication ticket."""

        # Generate secure random ticket
        ticket_str = secrets.token_urlsafe(32)

        # Create ticket data
        ticket = WebSocketTicket(
            ticket=ticket_str,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

        # Store in Redis with TTL
        key = f"{self.KEY_PREFIX}{ticket_str}"
        await self.redis.setex(key, self.ttl, ticket.to_json())

        return ticket_str
```

### Backend: Ticket Validation

```python
# In src/glp/agent/security/ticket_auth.py

async def validate_ticket(self, ticket: str) -> Optional[WebSocketTicket]:
    """Validate and consume a ticket (one-time use)."""

    if not ticket:
        return None

    key = f"{self.KEY_PREFIX}{ticket}"

    # Atomic get-and-delete (Redis 6.2+)
    try:
        data = await self.redis.getdel(key)
    except AttributeError:
        # Fallback to Lua script for atomicity
        data = await self.redis.eval(self._ATOMIC_GETDEL_SCRIPT, 1, key)

    if not data:
        return None

    # Parse and validate ticket data
    ticket_data = WebSocketTicket.from_json(data)

    # Verify ticket matches (defense in depth)
    if not secrets.compare_digest(ticket_data.ticket, ticket):
        return None

    # Check expiration with clock skew tolerance
    if ticket_data.is_expired(self.MAX_AGE):
        return None

    return ticket_data
```

### Frontend: React Hook (TypeScript)

```typescript
// In frontend/src/hooks/useChat.ts

export interface UseChatOptions {
  apiBaseUrl?: string
  authToken?: string  // JWT token
  getAuthToken?: () => string | null | Promise<string | null>
  autoReconnect?: boolean
}

export function useChat(options: UseChatOptions = {}) {
  const {
    apiBaseUrl = '/api/agent',
    authToken,
    getAuthToken,
    autoReconnect = true,
  } = options

  // Connect to WebSocket
  const connect = useCallback(async () => {
    // Get auth token
    const token = await resolveAuthToken()

    // Build headers for ticket request
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    // Add Authorization header if token available
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    // Step 1: Get ticket from REST API
    const ticketResponse = await fetch(`${apiBaseUrl}/ticket`, {
      method: 'POST',
      headers,
    })

    if (!ticketResponse.ok) {
      throw new Error(`Failed to get WebSocket ticket: ${ticketResponse.status}`)
    }

    const { ticket } = await ticketResponse.json()

    // Step 2: Connect WebSocket with ticket
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}${apiBaseUrl}/ws?ticket=${ticket}`

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      setState(prev => ({ ...prev, isConnected: true }))
      startHeartbeat()  // Send periodic pings
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      handleWebSocketEvent(data)
    }

    ws.onerror = () => {
      setState(prev => ({ ...prev, error: 'Connection failed' }))
    }

    ws.onclose = (event) => {
      setState(prev => ({ ...prev, isConnected: false }))

      // Auto-reconnect with exponential backoff
      if (autoReconnect && reconnectAttempts < MAX_ATTEMPTS) {
        setTimeout(connect, calculateBackoff())
      }
    }

    wsRef.current = ws
  }, [apiBaseUrl, authToken, autoReconnect])

  // Send chat message
  const sendMessage = useCallback((message: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'chat',
        message,
        conversation_id: conversationId,
      }))
    }
  }, [conversationId])

  return {
    connect,
    sendMessage,
    disconnect,
    // ... other methods
  }
}
```

### Frontend: Usage in Component

```typescript
// In frontend/src/components/ChatWidget.tsx

import { useChat } from '../hooks/useChat'

export function ChatWidget() {
  const {
    connect,
    disconnect,
    sendMessage,
    messages,
    isConnected,
    error,
  } = useChat({
    apiBaseUrl: '/api/agent',
    authToken: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...',  // From auth context
    autoReconnect: true,
  })

  useEffect(() => {
    connect()  // Connect on mount
    return () => disconnect()  // Disconnect on unmount
  }, [connect, disconnect])

  const handleSend = () => {
    sendMessage('Show me active devices')
  }

  return (
    <div>
      <div>Status: {isConnected ? 'Connected' : 'Disconnected'}</div>
      {error && <div>Error: {error}</div>}

      <div>
        {messages.map(msg => (
          <div key={msg.id}>
            <strong>{msg.role}:</strong> {msg.content}
          </div>
        ))}
      </div>

      <button onClick={handleSend} disabled={!isConnected}>
        Send
      </button>
    </div>
  )
}
```

## Error Handling

### WebSocket Close Codes

The server uses standard and custom WebSocket close codes:

| Code | Reason | Description |
|------|--------|-------------|
| 1000 | Normal Closure | Clean disconnect |
| 4001 | Invalid Ticket | Ticket validation failed (expired, invalid, or already used) |
| 4003 | Auth Not Configured | Server ticket auth not initialized |

### Client Error Handling

```typescript
ws.onclose = (event) => {
  switch (event.code) {
    case 4001:
      // Invalid ticket - need to get new ticket and reconnect
      console.error('Ticket invalid/expired - reconnecting...')
      reconnect()
      break

    case 4003:
      // Server misconfiguration - don't retry
      console.error('Server auth not configured')
      setState({ error: 'Service unavailable' })
      break

    default:
      // Unexpected disconnect - retry with backoff
      if (autoReconnect) {
        setTimeout(reconnect, calculateBackoff())
      }
  }
}
```

### Server Error Events

```python
# Send error to client
await websocket.send_json({
    "type": "error",
    "content": "Database connection failed",
    "error_type": "fatal",  # or "recoverable"
})
```

## Configuration

### Environment Variables

**JWT Configuration:**

```bash
# Required (for symmetric algorithms)
JWT_SECRET=your-secret-key-min-32-chars

# Required (for asymmetric algorithms)
JWT_PUBLIC_KEY=/path/to/public-key.pem
# Or inline:
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n..."

# Algorithm (default: HS256)
JWT_ALGORITHM=HS256  # or RS256, ES256, etc.

# Optional claim validation
JWT_ISSUER=https://auth.example.com
JWT_AUDIENCE=https://api.example.com

# Clock skew tolerance (default: 30 seconds)
JWT_CLOCK_SKEW_SECONDS=30

# Custom claim names (optional)
JWT_TENANT_ID_CLAIM=tenant_id
JWT_USER_ID_CLAIM=sub
JWT_SESSION_ID_CLAIM=session_id

# Dev mode (NEVER use in production!)
REQUIRE_AUTH=false  # Bypasses auth - use only for local development
```

**Redis Configuration:**

```bash
# Redis URL for ticket storage
REDIS_URL=redis://localhost:6379

# For production with authentication:
REDIS_URL=redis://:password@redis-host:6379/0
```

### Ticket TTL Configuration

```python
# In application startup code

ticket_auth = WebSocketTicketAuth(
    redis=redis_client,
    ttl=60,  # Customize TTL in seconds (default: 60)
)
```

### Security Best Practices

1. **Always use HTTPS/WSS in production** - Prevents token/ticket interception
2. **Use strong JWT secrets** - Minimum 32 characters, cryptographically random
3. **Enable JWT claim validation** - Configure issuer and audience checks
4. **Use Redis authentication** - Protect ticket storage with Redis password
5. **Monitor ticket usage** - Log and alert on unusual patterns
6. **Rotate JWT secrets** - Regular rotation of signing keys
7. **Use asymmetric algorithms** - RS256/ES256 for better key management

### Development Mode

For local development without authentication:

```bash
# .env.development
REQUIRE_AUTH=false
```

**Warning:** Never use `REQUIRE_AUTH=false` in production! This completely disables authentication and should only be used for local testing.

## Troubleshooting

### "Invalid or expired ticket"

**Causes:**
- Ticket already used (one-time use)
- Ticket expired (> 60 seconds old)
- Ticket not found in Redis
- Clock skew too large

**Solutions:**
- Request new ticket before each connection
- Connect immediately after receiving ticket
- Check Redis connectivity
- Verify system clocks are synchronized

### "Failed to get WebSocket ticket"

**Causes:**
- Invalid JWT token
- JWT token expired
- Missing Authorization header
- JWT configuration error

**Solutions:**
- Verify JWT token is valid and not expired
- Check Authorization header format: `Bearer <token>`
- Verify JWT_SECRET or JWT_PUBLIC_KEY is configured
- Check server logs for detailed error

### Connection Closes Immediately

**Causes:**
- Ticket validation failed
- WebSocket upgrade failed
- Network connectivity issues

**Solutions:**
- Check browser console for close code
- Verify ticket in URL query param
- Check server logs for validation errors
- Ensure WebSocket protocol matches (ws:// or wss://)

### "Ticket auth not configured"

**Causes:**
- Redis not connected
- WebSocketTicketAuth not initialized
- Dependencies not injected

**Solutions:**
- Verify Redis connection string
- Check application startup code
- Ensure `create_agent_dependencies()` is called

---

## Summary

The WebSocket authentication flow provides a secure, scalable approach to real-time communication:

1. **JWT Authentication** ensures only authorized users can request tickets
2. **Ticket Exchange** prevents JWT exposure in URLs and logs
3. **One-Time Use** prevents replay attacks
4. **Short TTL** limits attack window
5. **Tenant Isolation** ensures multi-tenant security
6. **Atomic Operations** prevent race conditions

This design balances security, usability, and performance while following industry best practices for WebSocket authentication.
