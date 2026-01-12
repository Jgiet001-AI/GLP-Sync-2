"""Domain entities and port interfaces for the agent module."""

from .entities import (
    ChatEvent,
    ChatEventType,
    Conversation,
    ErrorType,
    Memory,
    MemoryType,
    Message,
    MessageRole,
    ToolCall,
    ToolDefinition,
    ToolResult,
    UserContext,
)
from .ports import (
    IConversationStore,
    IEmbeddingProvider,
    ILLMProvider,
    IMCPClient,
    IMemoryStore,
    IToolExecutor,
)

__all__ = [
    # Entities
    "ChatEvent",
    "ChatEventType",
    "Conversation",
    "ErrorType",
    "Memory",
    "MemoryType",
    "Message",
    "MessageRole",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "UserContext",
    # Ports
    "IConversationStore",
    "IEmbeddingProvider",
    "ILLMProvider",
    "IMCPClient",
    "IMemoryStore",
    "IToolExecutor",
]
