# GreenLake Inventory Chatbot - Implementation Plan

**Version:** 4.0 (Codex-Validated)
**Created:** 2026-01-11
**Status:** Ready for Implementation

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Database Schema](#database-schema)
4. [Backend Structure](#backend-structure)
5. [LLM Provider Interface](#llm-provider-interface)
6. [Tool System](#tool-system)
7. [Memory System](#memory-system)
8. [Streaming Contract](#streaming-contract)
9. [Security](#security)
10. [Frontend Integration](#frontend-integration)
11. [Implementation Phases](#implementation-phases)
12. [Validation History](#validation-history)

---

## Overview

### Requirements
- **Chatbot UI**: Floating widget integrated throughout the app
- **Writes**: Use REST API (devices, subscriptions, applications via GreenLake v2beta1)
- **Reads**: Use FastMCP server (PostgreSQL with auditing)
- **CoT**: Chain of Thought reasoning with visualization
- **Memory**: Semantic (pgvector) + Long-term memory with fact extraction
- **Multi-Provider**: Support Claude, GPT-4, and Ollama

### Key Design Decisions
1. **Read operations** go through FastMCP (not direct PostgreSQL) to reuse existing auditing and vetted queries
2. **Write operations** go through DeviceManager with confirmation flow and audit logging
3. **CoT is never stored raw** - only redacted summaries for security
4. **Tenant isolation** is enforced at every layer (database, API, memory)
5. **Ticket-based WebSocket auth** instead of JWT in query string

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Frontend (React)                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │         Floating Chat Widget (ticket-based auth, streaming)         │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
└─────────────────────────────────┼──────────────────────────────────────────┘
                                  │ WebSocket (ticket = user + tenant + session)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FastAPI App (Existing + Agent Router)                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │     Agent Router (/api/chat) + Auth → derives tenant_id/user_id     │   │
│  └──────────────────────────────┬──────────────────────────────────────┘   │
│                                 │                                           │
│  ┌──────────────────────────────▼──────────────────────────────────────┐   │
│  │              Agent Orchestrator (tenant-scoped everything)          │   │
│  │  - Streaming with correlation IDs + error types                     │   │
│  │  - CoT redaction → thinking_summary only                            │   │
│  │  - Memory: per-model embedding + tenant/user scope                  │   │
│  └────────────┬──────────────────────────────┬─────────────────────────┘   │
│               │                              │                              │
│   ┌───────────▼──────────┐      ┌───────────▼──────────┐                   │
│   │  SecureMCPClient     │      │  DeviceManager       │                   │
│   │  (service token +    │      │  (existing, with     │                   │
│   │   user/tenant ctx)   │      │   audit logging)     │                   │
│   └──────────┬───────────┘      └──────────┬───────────┘                   │
│              │                              │                               │
└──────────────┼──────────────────────────────┼───────────────────────────────┘
               │ Service token (internal)     │
               ▼                              ▼
        ┌─────────────┐              ┌─────────────────┐
        │ FastMCP     │              │  GreenLake API  │
        │ Server      │              │  (v2beta1)      │
        │ (verifies   │              └─────────────────┘
        │  svc token) │
        └──────┬──────┘
               │
               ▼
        ┌─────────────┐
        │ PostgreSQL  │
        │ (pgvector)  │
        │ tenant_id   │
        │ scoped      │
        └─────────────┘
```

---

## Database Schema

### Extensions Required
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

### Agent Conversations
```sql
CREATE TABLE agent_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    summary TEXT,  -- Auto-generated for long conversations
    message_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_conversations_tenant_user ON agent_conversations(tenant_id, user_id, created_at DESC);

-- RLS
ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON agent_conversations
    USING (tenant_id = current_setting('app.tenant_id', true));
```

### Agent Messages
```sql
CREATE TABLE agent_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES agent_conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,

    -- CoT: ONLY redacted summary, never raw
    thinking_summary TEXT,

    -- Tool calls with correlation IDs
    tool_calls JSONB,  -- [{tool_call_id, name, arguments, result}]

    -- Embeddings with model tracking
    embedding vector(3072),
    embedding_model TEXT,
    embedding_dimension INTEGER,
    embedding_status TEXT DEFAULT 'pending' CHECK (embedding_status IN ('pending', 'processing', 'completed', 'failed')),

    -- Metadata
    model_used TEXT,
    tokens_used INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_messages_conversation ON agent_messages(conversation_id, created_at);
CREATE INDEX idx_messages_embedding_status ON agent_messages(embedding_status)
    WHERE embedding_status IN ('pending', 'failed');

-- Per-model partial indexes for embedding search
CREATE INDEX idx_messages_embedding_openai ON agent_messages
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    WHERE embedding_model = 'text-embedding-3-large' AND embedding IS NOT NULL;

CREATE INDEX idx_messages_embedding_claude ON agent_messages
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    WHERE embedding_model = 'claude-3-embed' AND embedding IS NOT NULL;
```

### Agent Memory
```sql
CREATE TABLE agent_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('fact', 'preference', 'entity', 'procedure')),
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,

    -- Embeddings
    embedding vector(3072),
    embedding_model TEXT,
    embedding_dimension INTEGER,

    -- Usage tracking
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,

    -- Source tracking
    source_conversation_id UUID REFERENCES agent_conversations(id) ON DELETE SET NULL,
    source_message_id UUID REFERENCES agent_messages(id) ON DELETE SET NULL,

    -- Lifecycle
    valid_from TIMESTAMPTZ DEFAULT NOW(),
    valid_until TIMESTAMPTZ,
    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    is_invalidated BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',

    -- User-scoped deduplication
    UNIQUE(tenant_id, user_id, content_hash)
);

-- Indexes
CREATE INDEX idx_memory_tenant_user ON agent_memory(tenant_id, user_id, memory_type)
    WHERE NOT is_invalidated;
CREATE INDEX idx_memory_ttl ON agent_memory(valid_until) WHERE valid_until IS NOT NULL;
CREATE INDEX idx_memory_confidence ON agent_memory(tenant_id, user_id, confidence DESC)
    WHERE NOT is_invalidated;
CREATE INDEX idx_memory_invalidated ON agent_memory(is_invalidated, updated_at)
    WHERE is_invalidated = TRUE;
CREATE INDEX idx_memory_last_accessed ON agent_memory(last_accessed_at)
    WHERE last_accessed_at IS NOT NULL;

-- Per-model partial indexes
CREATE INDEX idx_memory_embedding_openai ON agent_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    WHERE embedding_model = 'text-embedding-3-large' AND embedding IS NOT NULL;

-- RLS
ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON agent_memory
    USING (tenant_id = current_setting('app.tenant_id', true));
```

### Embedding Jobs Queue
```sql
CREATE TABLE agent_embedding_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    target_table TEXT NOT NULL CHECK (target_table IN ('agent_messages', 'agent_memory')),
    target_id UUID NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'dead')),
    retries INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,

    UNIQUE(target_table, target_id)
);

-- Indexes
CREATE INDEX idx_embedding_jobs_tenant ON agent_embedding_jobs(tenant_id, status, created_at)
    WHERE status = 'pending';
CREATE INDEX idx_embedding_jobs_status ON agent_embedding_jobs(status, created_at)
    WHERE status IN ('pending', 'failed');
CREATE INDEX idx_embedding_jobs_locked ON agent_embedding_jobs(locked_at, locked_by)
    WHERE locked_at IS NOT NULL;
```

### Audit Log
```sql
CREATE TABLE agent_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    payload JSONB,
    result JSONB,
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed', 'conflict')),
    error_message TEXT,
    idempotency_key TEXT,  -- For retry safety
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    UNIQUE(tenant_id, idempotency_key)
);

-- Indexes
CREATE INDEX idx_audit_tenant_user ON agent_audit_log(tenant_id, user_id, created_at DESC);
CREATE INDEX idx_audit_idempotency ON agent_audit_log(tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
```

### Memory Lifecycle Cleanup
```sql
CREATE OR REPLACE FUNCTION agent_memory_cleanup(p_tenant_id TEXT DEFAULT NULL) RETURNS void AS $$
BEGIN
    -- Invalidate expired memories
    UPDATE agent_memory SET is_invalidated = TRUE, updated_at = NOW()
    WHERE valid_until IS NOT NULL
      AND valid_until < NOW()
      AND NOT is_invalidated
      AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id);

    -- Decay unused low-confidence memories (30+ days without access)
    UPDATE agent_memory SET confidence = confidence * 0.9, updated_at = NOW()
    WHERE last_accessed_at < NOW() - INTERVAL '30 days'
      AND confidence > 0.1
      AND NOT is_invalidated
      AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id);

    -- Hard delete very old invalidated memories (90+ days)
    DELETE FROM agent_memory
    WHERE is_invalidated = TRUE
      AND updated_at < NOW() - INTERVAL '90 days'
      AND (p_tenant_id IS NULL OR tenant_id = p_tenant_id);
END;
$$ LANGUAGE plpgsql;
```

---

## Backend Structure

```
src/glp/agent/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── entities.py          # Message, Conversation, Memory, ToolCall, ChatEvent
│   └── ports.py             # ILLMProvider, IMemoryStore, IToolExecutor, IMCPClient
├── providers/
│   ├── __init__.py
│   ├── base.py              # BaseLLMProvider ABC
│   ├── anthropic.py         # Claude implementation
│   ├── openai.py            # GPT-4/GPT-5 implementation
│   └── ollama.py            # Local LLM implementation
├── memory/
│   ├── __init__.py
│   ├── semantic.py          # Vector-based semantic memory search
│   ├── long_term.py         # Fact extraction and storage
│   ├── conversation.py      # Conversation history management
│   └── embedding_worker.py  # Background embedding pipeline
├── tools/
│   ├── __init__.py
│   ├── registry.py          # Tool registration and routing
│   ├── mcp_client.py        # Secure FastMCP client
│   └── write_executor.py    # DeviceManager wrapper with audit
├── security/
│   ├── __init__.py
│   ├── cot_redactor.py      # Chain of thought redaction
│   ├── ticket_auth.py       # WebSocket ticket authentication
│   └── service_auth.py      # Service-to-service auth
├── orchestrator.py          # Main agent orchestrator
└── api/
    ├── __init__.py
    ├── router.py            # FastAPI router
    ├── schemas.py           # Pydantic models
    └── websocket.py         # WebSocket streaming handler
```

---

## LLM Provider Interface

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from enum import Enum

class ChatEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    TOOL_RESULT = "tool_result"
    CONFIRMATION_REQUIRED = "confirmation_required"
    CONFIRMATION_RESPONSE = "confirmation_response"
    ERROR = "error"
    CANCEL = "cancel"
    DONE = "done"

class ErrorType(str, Enum):
    RECOVERABLE = "recoverable"
    FATAL = "fatal"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"

@dataclass
class ChatEvent:
    type: ChatEventType
    sequence: int
    data: Optional[Any] = None
    tool_call_id: Optional[str] = None
    confirmation_id: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

class ILLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition],
        system_prompt: str,
        stream: bool = True,
    ) -> AsyncIterator[ChatEvent]:
        """Generate response with streaming events."""
        pass

    @abstractmethod
    async def embed(self, text: str) -> tuple[list[float], str, int]:
        """Generate embedding. Returns (vector, model_name, dimension)."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier."""
        pass
```

---

## Tool System

### Read Tools (via FastMCP)
```python
class SecureMCPClient:
    """Client for FastMCP with service-to-service auth."""

    def __init__(self, mcp_url: str, service_token: str):
        self.mcp_url = mcp_url
        self.service_token = service_token

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        user_context: UserContext,
    ) -> ToolResult:
        headers = {
            "Authorization": f"Bearer {self.service_token}",
            "X-User-ID": user_context.user_id,
            "X-Tenant-ID": user_context.tenant_id,
            "X-Request-ID": str(uuid4()),
        }

        async with self.circuit_breaker:
            response = await self.http.post(
                f"{self.mcp_url}/tools/{tool_name}",
                json=arguments,
                headers=headers,
                timeout=30,
            )

        return ToolResult.parse(response)
```

### Write Tools (via DeviceManager)
```python
class WriteToolExecutor:
    """Execute write operations with audit logging."""

    async def execute(
        self,
        tool_call: ToolCall,
        user_context: UserContext,
        idempotency_key: Optional[str] = None,
    ) -> WriteResult:
        # Check for duplicate (idempotency)
        if idempotency_key:
            existing = await self.audit.get_by_idempotency(
                user_context.tenant_id,
                idempotency_key,
            )
            if existing and existing.status == 'completed':
                return existing.result

        # Log intent
        audit_id = await self.audit.create(
            tenant_id=user_context.tenant_id,
            user_id=user_context.user_id,
            action=tool_call.name,
            payload=tool_call.arguments,
            idempotency_key=idempotency_key,
        )

        try:
            result = await self.device_manager.execute(tool_call)
            await self.audit.complete(audit_id, result=result)
            return result
        except ConcurrentModificationError:
            await self.audit.fail(audit_id, status='conflict')
            raise
        except Exception as e:
            await self.audit.fail(audit_id, error=str(e))
            raise
```

---

## Memory System

### Semantic Memory Search
```python
class SemanticMemoryStore:
    """Vector-based memory with tenant isolation."""

    async def search(
        self,
        query: str,
        embedding_model: str,
        tenant_id: str,
        user_id: str,
        limit: int = 10,
    ) -> list[Memory]:
        # Generate embedding for query
        embedding, model, dimension = await self.llm.embed(query)

        # Search with mandatory model filtering
        return await self.db.fetch("""
            SELECT *, embedding <=> $1::vector AS distance
            FROM agent_memory
            WHERE tenant_id = $2
              AND user_id = $3
              AND embedding_model = $4
              AND NOT is_invalidated
            ORDER BY distance
            LIMIT $5
        """, embedding, tenant_id, user_id, embedding_model, limit)
```

### Fact Extraction
```python
class FactExtractor:
    """Extract facts from assistant responses."""

    EXTRACTION_PROMPT = """Extract key facts from this conversation response.
    Return as JSON array: [{type: "fact"|"preference"|"entity", content: "...", confidence: 0.0-1.0}]

    Types:
    - fact: Objective information (e.g., "Device X has serial number Y")
    - preference: User preferences (e.g., "User prefers detailed explanations")
    - entity: Named entities (e.g., "San Jose data center")
    """

    async def extract(self, content: str) -> list[Fact]:
        response = await self.llm.chat([
            {"role": "system", "content": self.EXTRACTION_PROMPT},
            {"role": "user", "content": content},
        ])
        return self._parse_facts(response)

    async def store(self, facts: list[Fact], context: UserContext):
        for fact in facts:
            content_hash = hashlib.sha256(fact.content.encode()).hexdigest()
            await self.db.execute("""
                INSERT INTO agent_memory (tenant_id, user_id, memory_type, content, content_hash, confidence)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (tenant_id, user_id, content_hash)
                DO UPDATE SET confidence = GREATEST(agent_memory.confidence, $6), updated_at = NOW()
            """, context.tenant_id, context.user_id, fact.type, fact.content, content_hash, fact.confidence)
```

### Embedding Worker
```python
class EmbeddingWorker:
    """Background worker for embedding generation."""

    async def process_batch(self, batch_size: int = 10):
        async with self.db.transaction():
            jobs = await self.db.fetch("""
                UPDATE agent_embedding_jobs
                SET status = 'processing', locked_at = NOW(), locked_by = $1
                WHERE id IN (
                    SELECT id FROM agent_embedding_jobs
                    WHERE status = 'pending'
                    ORDER BY created_at
                    LIMIT $2
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING *
            """, self.worker_id, batch_size)

            for job in jobs:
                try:
                    await self._process_job(job)
                except Exception as e:
                    await self._handle_failure(job, e)

    async def _process_job(self, job):
        if job.target_table == 'agent_messages':
            record = await self.db.fetchrow(
                "SELECT content FROM agent_messages WHERE id = $1",
                job.target_id,
            )
        else:
            record = await self.db.fetchrow(
                "SELECT content FROM agent_memory WHERE id = $1",
                job.target_id,
            )

        if not record:
            return  # Record deleted, skip

        embedding, model, dimension = await self.llm.embed(record['content'])

        await self.db.execute(f"""
            UPDATE {job.target_table}
            SET embedding = $1, embedding_model = $2, embedding_dimension = $3, embedding_status = 'completed'
            WHERE id = $4
        """, embedding, model, dimension, job.target_id)

        await self.db.execute("""
            UPDATE agent_embedding_jobs
            SET status = 'completed', processed_at = NOW(), locked_at = NULL
            WHERE id = $1
        """, job.id)
```

---

## Streaming Contract

### Event Types
| Event | Description | Fields |
|-------|-------------|--------|
| `text_delta` | Partial text token | `data: str` |
| `thinking_delta` | CoT content (redacted) | `data: str` |
| `tool_call_start` | Tool invocation begins | `tool_call_id, data: {name, arguments}` |
| `tool_call_delta` | Streaming tool args | `tool_call_id, data: str` |
| `tool_call_end` | Tool invocation ends | `tool_call_id` |
| `tool_result` | Tool execution result | `tool_call_id, data: any` |
| `confirmation_required` | Write needs approval | `confirmation_id, data: {action, description}` |
| `confirmation_response` | User approved/denied | `confirmation_id, data: {approved: bool}` |
| `error` | Error occurred | `error: str, error_type: ErrorType` |
| `cancel` | Stream cancelled | - |
| `done` | Stream finished | - |

### Ordering Guarantees
- Events include `sequence` number for ordering
- `tool_call_id` links all events for a single tool call
- `confirmation_id` links confirmation request/response
- `event_id` enables idempotency

---

## Security

### CoT Redaction
```python
class CoTRedactor:
    PATTERNS = [
        (r'password[=:]\s*\S+', '[PASSWORD]'),
        (r'api[-_]?key[=:]\s*\S+', '[API_KEY]'),
        (r'secret[=:]\s*\S+', '[SECRET]'),
        (r'token[=:]\s*\S+', '[TOKEN]'),
        (r'bearer\s+\S+', 'Bearer [REDACTED]'),
        (r'\b[A-Za-z0-9+/]{40,}={0,2}\b', '[BASE64_REDACTED]'),
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP_ADDRESS]'),
    ]

    def redact(self, text: str) -> str:
        for pattern, replacement in self.PATTERNS:
            text = re.sub(pattern, replacement, text, flags=re.I)
        return text
```

### Ticket Authentication
```python
@dataclass
class WebSocketTicket:
    ticket: str
    user_id: str
    tenant_id: str
    session_id: str
    conversation_id: Optional[str]
    created_at: float

class WebSocketTicketAuth:
    async def create_ticket(
        self,
        user_id: str,
        tenant_id: str,
        session_id: str,
        conversation_id: Optional[str] = None,
    ) -> str:
        ticket = secrets.token_urlsafe(32)
        data = WebSocketTicket(
            ticket=ticket,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            conversation_id=conversation_id,
            created_at=time.time(),
        )
        await self.redis.setex(f"ws_ticket:{ticket}", 60, data.json())
        return ticket

    async def validate_ticket(self, ticket: str) -> Optional[WebSocketTicket]:
        key = f"ws_ticket:{ticket}"
        data = await self.redis.getdel(key)  # Atomic get + delete
        if not data:
            return None

        ticket_data = WebSocketTicket.parse_raw(data)

        # Validate TTL (clock skew tolerance)
        if time.time() - ticket_data.created_at > 120:
            return None

        return ticket_data
```

### Service-to-Service Auth
```python
def verify_internal_service_token(token: str) -> bool:
    """Verify JWT signed by internal service key."""
    try:
        payload = jwt.decode(
            token,
            settings.INTERNAL_SERVICE_SECRET,
            algorithms=["HS256"],
            audience="fastmcp",
        )
        return payload.get("service") == "agent-orchestrator"
    except jwt.InvalidTokenError:
        return False
```

---

## Frontend Integration

### Chat Widget Component
```typescript
// frontend/src/components/chat/ChatWidget.tsx
import { useAuth } from '../hooks/useAuth';
import { useEffect, useRef, useState } from 'react';

interface ChatEvent {
  type: string;
  sequence: number;
  data?: any;
  tool_call_id?: string;
  confirmation_id?: string;
  error?: string;
  error_type?: string;
}

export const ChatWidget: React.FC = () => {
  const { token, user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentThinking, setCurrentThinking] = useState<string>('');
  const wsRef = useRef<WebSocket | null>(null);
  const ticketRef = useRef<string | null>(null);

  // Get ticket for WebSocket connection
  const getTicket = async () => {
    const response = await fetch('/api/chat/ticket', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const { ticket } = await response.json();
    return ticket;
  };

  // Connect WebSocket
  const connect = async () => {
    const ticket = await getTicket();
    ticketRef.current = ticket;

    wsRef.current = new WebSocket(`ws://${location.host}/api/chat/ws?ticket=${ticket}`);

    wsRef.current.onmessage = (event) => {
      const data: ChatEvent = JSON.parse(event.data);
      handleEvent(data);
    };

    wsRef.current.onclose = (event) => {
      if (event.code === 4001) {
        // Auth failed, reconnect with new ticket
        setTimeout(connect, 1000);
      }
    };
  };

  const handleEvent = (event: ChatEvent) => {
    switch (event.type) {
      case 'text_delta':
        // Append to current assistant message
        break;
      case 'thinking_delta':
        setCurrentThinking(prev => prev + event.data);
        break;
      case 'tool_call_start':
        // Show tool execution indicator
        break;
      case 'confirmation_required':
        // Show confirmation modal
        showConfirmationModal(event);
        break;
      case 'error':
        handleError(event);
        break;
      case 'done':
        setCurrentThinking('');
        break;
    }
  };

  // ... rest of component
};
```

### CSS for Floating Widget
```css
.chat-widget {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 9999;
}

.chat-widget-button {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: #0070f3;
  color: white;
  border: none;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.chat-panel {
  position: fixed;
  bottom: 90px;
  right: 20px;
  width: 400px;
  height: 600px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
}

.thinking-indicator {
  background: #f5f5f5;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
  color: #666;
  max-height: 100px;
  overflow-y: auto;
}
```

---

## Implementation Phases

### Phase 1: Database & Core (Week 1)
1. Create migration for agent tables
2. Set up pgvector extension
3. Implement RLS policies
4. Create agent module structure
5. Implement domain entities

### Phase 2: LLM Providers (Week 1-2)
1. Implement base provider interface
2. Add Anthropic Claude provider
3. Add OpenAI provider
4. Add embedding generation
5. Create provider factory

### Phase 3: Memory System (Week 2)
1. Implement semantic memory store
2. Build fact extraction pipeline
3. Create embedding worker
4. Add conversation management
5. Set up background job processing

### Phase 4: Tool System (Week 2-3)
1. Create SecureMCPClient
2. Implement write tool executor
3. Add audit logging
4. Set up circuit breakers
5. Implement confirmation flow

### Phase 5: Orchestrator (Week 3)
1. Build main orchestrator
2. Implement streaming handler
3. Add CoT redaction
4. Create WebSocket endpoint
5. Integrate all components

### Phase 6: Frontend (Week 3-4)
1. Build ChatWidget component
2. Implement streaming event handling
3. Add CoT visualization
4. Create confirmation modals
5. Integrate with existing auth

### Phase 7: Testing & Polish (Week 4)
1. Write unit tests
2. Add integration tests
3. Security testing
4. Performance optimization
5. Documentation

---

## Validation History

| Round | Reviewer | Issues Found | Resolution |
|-------|----------|--------------|------------|
| 1 | Codex (gpt-5-codex, high) | 8 critical: Direct DB bypass, missing indexes, CoT storage, header spoofing | v2: Use FastMCP, add indexes, encrypt CoT |
| 2 | Codex (gpt-5.2-codex, xhigh) | 6 issues: Missing tenant columns, WS auth, streaming contract | v3: Add tenant_id everywhere, ticket auth |
| 3 | Codex (gpt-5.2-codex, xhigh) | 3 blockers: Tenant isolation, MCP auth, embedding partitioning | v4: RLS, service tokens, per-model indexes |
| 4 | Codex (gpt-5, low) | 0 blockers, operational items | Ready for implementation |

### Operational Items (Address During Implementation)
- PostgreSQL RLS policies on all tenant tables
- Rate limiting per-tenant/user
- Idempotency keys for write operations
- ivfflat index maintenance (ANALYZE, REINDEX)
- Service token rotation strategy
- Per-tenant metrics and tracing
