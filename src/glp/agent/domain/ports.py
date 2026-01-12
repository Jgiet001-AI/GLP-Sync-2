"""
Port interfaces (abstract base classes) for the agent module.

These define the contracts that adapters must implement.
Following the Ports & Adapters (Hexagonal) architecture pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional
from uuid import UUID

if TYPE_CHECKING:
    from .entities import (
        ChatEvent,
        Conversation,
        Memory,
        MemoryType,
        Message,
        ToolCall,
        ToolDefinition,
        ToolResult,
        UserContext,
    )


# ============================================
# LLM Provider Interface
# ============================================


class ILLMProvider(ABC):
    """Interface for LLM providers (Claude, GPT, Ollama, etc.).

    Implementations handle the specifics of each LLM API while
    providing a consistent interface to the orchestrator.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier (e.g., 'claude-3-opus', 'gpt-4')."""
        pass

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Return True if this provider supports streaming responses."""
        pass

    @property
    @abstractmethod
    def supports_tools(self) -> bool:
        """Return True if this provider supports tool/function calling."""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Generate a response to the conversation.

        Args:
            messages: Conversation history
            tools: Available tools for the model to use
            system_prompt: System prompt to prepend
            stream: Whether to stream the response
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            ChatEvent objects representing the streaming response
        """
        pass

    @abstractmethod
    async def embed(self, text: str) -> tuple[list[float], str, int]:
        """Generate an embedding for the given text.

        Args:
            text: Text to embed

        Returns:
            Tuple of (embedding_vector, model_name, dimension)
        """
        pass

    async def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
    ) -> str:
        """Generate a simple text completion (non-streaming).

        Convenience method that wraps chat() for simple completions.
        Used by FactExtractor and ConversationSummarizer.

        Args:
            prompt: The prompt to complete
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            Generated text response
        """
        from .entities import ChatEventType, Message, MessageRole

        messages = [Message(role=MessageRole.USER, content=prompt)]
        result_text = ""

        async for event in self.chat(
            messages=messages,
            system_prompt=system_prompt,
            stream=True,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            if event.type == ChatEventType.TEXT_DELTA and event.content:
                result_text += event.content
            elif event.type == ChatEventType.ERROR:
                raise RuntimeError(event.error or "LLM completion failed")

        return result_text


# ============================================
# Embedding Provider Interface
# ============================================


class IEmbeddingProvider(ABC):
    """Interface for embedding-only providers.

    Separate from ILLMProvider for cases where you want to use
    a different model for embeddings than for chat.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the embedding model name."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the embedding dimension."""
        pass

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate an embedding for the given text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass


# ============================================
# Conversation Store Interface
# ============================================


class IConversationStore(ABC):
    """Interface for conversation persistence."""

    @abstractmethod
    async def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation."""
        pass

    @abstractmethod
    async def get(
        self, conversation_id: UUID, context: UserContext
    ) -> Optional[Conversation]:
        """Get a conversation by ID (with tenant isolation)."""
        pass

    @abstractmethod
    async def list(
        self,
        context: UserContext,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for a user (with tenant isolation)."""
        pass

    @abstractmethod
    async def add_message(
        self, conversation_id: UUID, message: Message, context: UserContext
    ) -> Message:
        """Add a message to a conversation."""
        pass

    @abstractmethod
    async def get_messages(
        self,
        conversation_id: UUID,
        context: UserContext,
        limit: int = 50,
        before: Optional[UUID] = None,
    ) -> list[Message]:
        """Get messages from a conversation."""
        pass

    @abstractmethod
    async def update_summary(
        self, conversation_id: UUID, summary: str, context: UserContext
    ) -> None:
        """Update the conversation summary."""
        pass

    @abstractmethod
    async def delete(self, conversation_id: UUID, context: UserContext) -> bool:
        """Delete a conversation and all its messages."""
        pass


# ============================================
# Memory Store Interface
# ============================================


class IMemoryStore(ABC):
    """Interface for long-term memory persistence and retrieval."""

    @abstractmethod
    async def store(self, memory: Memory) -> Memory:
        """Store a new memory (handles deduplication via content_hash)."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        context: UserContext,
        embedding_model: str,
        limit: int = 10,
        memory_types: Optional[list[MemoryType]] = None,
        min_confidence: float = 0.0,
    ) -> list[tuple[Memory, float]]:
        """Search memories by semantic similarity.

        Args:
            query: Search query text
            context: User context for tenant isolation
            embedding_model: Model name to filter by (required)
            limit: Maximum results
            memory_types: Filter by memory types
            min_confidence: Minimum confidence threshold

        Returns:
            List of (Memory, distance) tuples sorted by relevance
        """
        pass

    @abstractmethod
    async def get(
        self, memory_id: UUID, context: UserContext
    ) -> Optional[Memory]:
        """Get a memory by ID."""
        pass

    @abstractmethod
    async def update_access(self, memory_id: UUID) -> None:
        """Update access tracking (count and timestamp)."""
        pass

    @abstractmethod
    async def invalidate(self, memory_id: UUID, context: UserContext) -> bool:
        """Soft-delete a memory."""
        pass

    @abstractmethod
    async def get_by_source(
        self,
        conversation_id: Optional[UUID],
        message_id: Optional[UUID],
        context: UserContext,
    ) -> list[Memory]:
        """Get memories extracted from a specific conversation/message."""
        pass

    @abstractmethod
    async def cleanup(self, tenant_id: Optional[str] = None) -> dict[str, int]:
        """Run memory lifecycle cleanup.

        Returns:
            Dict with counts: invalidated, decayed, deleted
        """
        pass


# ============================================
# MCP Client Interface
# ============================================


class IMCPClient(ABC):
    """Interface for FastMCP client (read operations)."""

    @abstractmethod
    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: UserContext,
        timeout: float = 30.0,
    ) -> ToolResult:
        """Call a FastMCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            context: User context for audit
            timeout: Maximum execution time in seconds

        Returns:
            ToolResult with success/failure and data
        """
        pass

    async def execute_tool_call(
        self,
        tool_call: ToolCall,
        context: UserContext,
        timeout: float = 30.0,
    ) -> ToolCall:
        """Execute a tool call and populate result.

        Convenience wrapper around call_tool() that takes a ToolCall object.
        Used by ToolRegistry for consistent interface.

        Args:
            tool_call: Tool call from LLM
            context: User context for audit
            timeout: Maximum execution time in seconds

        Returns:
            ToolCall with result populated
        """
        result = await self.call_tool(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            context=context,
            timeout=timeout,
        )

        tool_call.result = {
            "success": result.success,
            "data": result.data,
            "error": result.error,
        } if not result.success else result.data

        return tool_call

    @abstractmethod
    async def list_tools(self) -> list[ToolDefinition]:
        """List all available tools from FastMCP server."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the FastMCP server is healthy."""
        pass


# ============================================
# Tool Executor Interface
# ============================================


class IToolExecutor(ABC):
    """Interface for executing tools (both read and write)."""

    @abstractmethod
    async def execute(
        self,
        tool_call: ToolCall,
        context: UserContext,
        idempotency_key: Optional[str] = None,
    ) -> ToolResult:
        """Execute a tool call.

        Automatically routes to MCP (reads) or DeviceManager (writes).

        Args:
            tool_call: Tool call to execute
            context: User context for audit and isolation
            idempotency_key: Optional key for retry safety

        Returns:
            ToolResult with execution outcome
        """
        pass

    @abstractmethod
    def is_read_tool(self, tool_name: str) -> bool:
        """Check if a tool is read-only."""
        pass

    @abstractmethod
    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation."""
        pass

    @abstractmethod
    async def get_all_tools(self) -> list[ToolDefinition]:
        """Get all available tools (read + write)."""
        pass


# ============================================
# Audit Log Interface
# ============================================


class IAuditLog(ABC):
    """Interface for audit logging of write operations."""

    @abstractmethod
    async def create(
        self,
        tenant_id: str,
        user_id: str,
        action: str,
        payload: dict[str, Any],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> UUID:
        """Create an audit log entry for a pending operation."""
        pass

    @abstractmethod
    async def complete(
        self,
        audit_id: UUID,
        result: dict[str, Any],
    ) -> None:
        """Mark an audit entry as completed."""
        pass

    @abstractmethod
    async def fail(
        self,
        audit_id: UUID,
        error: str,
        status: str = "failed",
    ) -> None:
        """Mark an audit entry as failed."""
        pass

    @abstractmethod
    async def get_by_idempotency_key(
        self,
        tenant_id: str,
        idempotency_key: str,
    ) -> Optional[dict[str, Any]]:
        """Get an audit entry by idempotency key."""
        pass
