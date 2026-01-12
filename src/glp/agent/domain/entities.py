"""
Domain entities for the agent chatbot.

These are pure domain objects with no infrastructure dependencies.
They define the core data structures used throughout the agent module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

# ============================================
# User Context
# ============================================


@dataclass(frozen=True)
class UserContext:
    """User context for tenant isolation and audit tracking.

    Attributes:
        tenant_id: Tenant identifier for multi-tenancy isolation
        user_id: User identifier within the tenant
        session_id: Optional session identifier for tracking
        request_id: Optional request ID for distributed tracing
    """

    tenant_id: str
    user_id: str
    session_id: Optional[str] = None
    request_id: Optional[str] = None

    def __post_init__(self):
        if not self.tenant_id:
            raise ValueError("tenant_id is required")
        if not self.user_id:
            raise ValueError("user_id is required")


# ============================================
# Message Types
# ============================================


class MessageRole(str, Enum):
    """Role of a message in a conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """A single message in a conversation.

    Attributes:
        id: Unique message identifier
        conversation_id: Parent conversation ID
        role: Message role (user, assistant, system, tool)
        content: Message text content
        thinking_summary: Redacted CoT summary (never raw)
        tool_calls: List of tool calls made in this message
        embedding: Vector embedding for semantic search
        embedding_model: Model used to generate embedding
        embedding_dimension: Dimension of the embedding vector
        model_used: LLM model used to generate this message
        tokens_used: Token count for this message
        latency_ms: Response latency in milliseconds
        created_at: Creation timestamp
    """

    role: MessageRole
    content: str
    id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    thinking_summary: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    embedding: Optional[list[float]] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = datetime.utcnow()


# ============================================
# Conversation
# ============================================


@dataclass
class Conversation:
    """A chat conversation containing multiple messages.

    Attributes:
        id: Unique conversation identifier
        tenant_id: Tenant for isolation
        user_id: User who owns this conversation
        title: Conversation title (auto-generated or user-set)
        summary: Auto-generated summary for long conversations
        messages: List of messages in this conversation
        message_count: Total message count
        metadata: Additional metadata
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    tenant_id: str
    user_id: str
    id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    messages: list[Message] = field(default_factory=list)
    message_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.id is None:
            self.id = uuid.uuid4()
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = self.created_at

    def add_message(self, message: Message) -> None:
        """Add a message to this conversation."""
        message.conversation_id = self.id
        self.messages.append(message)
        self.message_count += 1
        self.updated_at = datetime.utcnow()


# ============================================
# Memory Types
# ============================================


class MemoryType(str, Enum):
    """Type of long-term memory."""

    FACT = "fact"  # Objective information
    PREFERENCE = "preference"  # User preferences
    ENTITY = "entity"  # Named entities (devices, locations, etc.)
    PROCEDURE = "procedure"  # How-to knowledge


@dataclass
class Memory:
    """A piece of long-term memory.

    Attributes:
        id: Unique memory identifier
        tenant_id: Tenant for isolation
        user_id: User who owns this memory
        memory_type: Type of memory (fact, preference, entity, procedure)
        content: Memory content text
        content_hash: SHA-256 hash for deduplication
        embedding: Vector embedding for semantic search
        embedding_model: Model used for embedding
        embedding_dimension: Embedding dimension
        access_count: Number of times this memory was retrieved
        last_accessed_at: Last retrieval timestamp
        source_conversation_id: Conversation this was extracted from
        source_message_id: Message this was extracted from
        valid_from: When this memory became valid
        valid_until: When this memory expires (None = forever)
        confidence: Confidence score 0-1, decays over time
        is_invalidated: Soft delete flag
        metadata: Additional metadata
        created_at: Creation timestamp
        updated_at: Last update timestamp
    """

    tenant_id: str
    user_id: str
    memory_type: MemoryType
    content: str
    id: Optional[uuid.UUID] = None
    content_hash: Optional[str] = None
    embedding: Optional[list[float]] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    source_conversation_id: Optional[uuid.UUID] = None
    source_message_id: Optional[uuid.UUID] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    confidence: float = 1.0
    is_invalidated: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        import hashlib

        if self.id is None:
            self.id = uuid.uuid4()
        if self.content_hash is None:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()
        if self.valid_from is None:
            self.valid_from = datetime.utcnow()
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = self.created_at


# ============================================
# Tool System
# ============================================


@dataclass
class ToolDefinition:
    """Definition of an available tool.

    Attributes:
        name: Tool name (e.g., 'search_devices')
        description: Human-readable description
        parameters: JSON Schema for parameters
        is_read_only: True if tool only reads data
        requires_confirmation: True if write needs user approval
        timeout_seconds: Maximum execution time
    """

    name: str
    description: str
    parameters: dict[str, Any]
    is_read_only: bool = True
    requires_confirmation: bool = False
    timeout_seconds: int = 30

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_format(self) -> dict[str, Any]:
        """Convert to Anthropic tool use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


@dataclass
class ToolCall:
    """A tool call made by the LLM.

    Attributes:
        id: Unique tool call identifier (for correlation)
        name: Tool name being called
        arguments: Arguments passed to the tool
        result: Result from tool execution (set after execution)
        error: Error message if execution failed
        executed_at: When the tool was executed
    """

    name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    result: Optional[Any] = None
    error: Optional[str] = None
    executed_at: Optional[datetime] = None

    @property
    def is_executed(self) -> bool:
        """Check if this tool call has been executed."""
        return self.executed_at is not None


@dataclass
class ToolResult:
    """Result from a tool execution.

    Attributes:
        tool_call_id: ID of the tool call this is a result for
        success: Whether execution succeeded
        data: Result data (if successful)
        error: Error message (if failed)
        latency_ms: Execution time in milliseconds
    """

    tool_call_id: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None


# ============================================
# Streaming Events
# ============================================


class ChatEventType(str, Enum):
    """Types of streaming chat events."""

    TEXT_DELTA = "text_delta"  # Partial text token
    THINKING_DELTA = "thinking_delta"  # CoT content (redacted)
    TOOL_CALL_START = "tool_call_start"  # Tool invocation begins
    TOOL_CALL_DELTA = "tool_call_delta"  # Streaming tool arguments
    TOOL_CALL_END = "tool_call_end"  # Tool invocation ends
    TOOL_RESULT = "tool_result"  # Tool execution result
    CONFIRMATION_REQUIRED = "confirmation_required"  # Write needs approval
    CONFIRMATION_RESPONSE = "confirmation_response"  # User approved/denied
    ERROR = "error"  # Error occurred
    CANCEL = "cancel"  # Stream cancelled
    DONE = "done"  # Stream finished


class ErrorType(str, Enum):
    """Types of errors in streaming."""

    RECOVERABLE = "recoverable"  # Can retry
    FATAL = "fatal"  # Must abort
    TIMEOUT = "timeout"  # Tool/LLM timeout
    RATE_LIMIT = "rate_limit"  # Rate limited, back off


@dataclass
class ChatEvent:
    """A streaming chat event.

    Attributes:
        type: Event type
        sequence: Sequence number for ordering
        content: Text content (for TEXT_DELTA, THINKING_DELTA, TOOL_RESULT, ERROR)
        tool_call_id: Links TOOL_CALL_* events
        tool_name: Tool name (for TOOL_CALL_START)
        tool_arguments: Tool arguments (for TOOL_CALL_END)
        confirmation_id: Links CONFIRMATION_* events
        error: Error message (for ERROR events)
        error_type: Type of error
        metadata: Additional event metadata
        correlation_id: Request correlation ID for tracing
        data: Legacy event data (deprecated, use specific fields)
        event_id: Unique event ID for idempotency
    """

    type: ChatEventType
    sequence: int
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[dict[str, Any]] = None
    confirmation_id: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[ErrorType] = None
    metadata: Optional[dict[str, Any]] = None
    correlation_id: Optional[str] = None
    data: Optional[Any] = None  # Legacy field for backward compatibility
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "type": self.type.value,
            "sequence": self.sequence,
            "event_id": self.event_id,
        }
        if self.content is not None:
            result["content"] = self.content
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.tool_name is not None:
            result["tool_name"] = self.tool_name
        if self.tool_arguments is not None:
            result["tool_arguments"] = self.tool_arguments
        if self.confirmation_id is not None:
            result["confirmation_id"] = self.confirmation_id
        if self.error is not None:
            result["error"] = self.error
        if self.error_type is not None:
            result["error_type"] = self.error_type.value
        if self.metadata is not None:
            result["metadata"] = self.metadata
        if self.correlation_id is not None:
            result["correlation_id"] = self.correlation_id
        # Include data for backward compatibility
        if self.data is not None:
            result["data"] = self.data
        return result

    @classmethod
    def text_delta(cls, text: str, sequence: int) -> ChatEvent:
        """Create a text delta event."""
        return cls(type=ChatEventType.TEXT_DELTA, sequence=sequence, content=text)

    @classmethod
    def thinking_delta(cls, text: str, sequence: int) -> ChatEvent:
        """Create a thinking delta event."""
        return cls(type=ChatEventType.THINKING_DELTA, sequence=sequence, content=text)

    @classmethod
    def tool_call_start(
        cls, tool_call_id: str, name: str, sequence: int
    ) -> ChatEvent:
        """Create a tool call start event."""
        return cls(
            type=ChatEventType.TOOL_CALL_START,
            sequence=sequence,
            tool_call_id=tool_call_id,
            tool_name=name,
        )

    @classmethod
    def tool_result(
        cls, tool_call_id: str, result: Any, sequence: int
    ) -> ChatEvent:
        """Create a tool result event."""
        return cls(
            type=ChatEventType.TOOL_RESULT,
            sequence=sequence,
            tool_call_id=tool_call_id,
            content=str(result) if result is not None else None,
        )

    @classmethod
    def tool_call_end(
        cls, tool_call_id: str, arguments: dict[str, Any], sequence: int
    ) -> ChatEvent:
        """Create a tool call end event."""
        return cls(
            type=ChatEventType.TOOL_CALL_END,
            sequence=sequence,
            tool_call_id=tool_call_id,
            tool_arguments=arguments,
        )

    @classmethod
    def confirmation_required(
        cls, confirmation_id: str, action: str, description: str, sequence: int
    ) -> ChatEvent:
        """Create a confirmation required event."""
        return cls(
            type=ChatEventType.CONFIRMATION_REQUIRED,
            sequence=sequence,
            confirmation_id=confirmation_id,
            content=description,
            metadata={"action": action, "description": description},
        )

    @classmethod
    def error_event(
        cls, message: str, error_type: ErrorType, sequence: int
    ) -> ChatEvent:
        """Create an error event."""
        return cls(
            type=ChatEventType.ERROR,
            sequence=sequence,
            content=message,
            error=message,
            error_type=error_type,
        )

    @classmethod
    def done(cls, sequence: int, metadata: Optional[dict[str, Any]] = None) -> ChatEvent:
        """Create a done event."""
        return cls(type=ChatEventType.DONE, sequence=sequence, metadata=metadata)
