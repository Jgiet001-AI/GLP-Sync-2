"""
GreenLake Inventory Chatbot Agent Module.

This module provides an AI-powered chatbot for querying and managing
HPE GreenLake device and subscription inventory.

Architecture:
- Domain: Core entities and port interfaces
- Providers: LLM provider implementations (Claude, GPT, Ollama)
- Memory: Semantic and long-term memory with pgvector
- Tools: Read (FastMCP) and write (DeviceManager) tool execution
- Security: CoT redaction, auth, and tenant isolation
- Orchestrator: Main agent coordination logic
- API: FastAPI router and WebSocket streaming

Key Features:
- Multi-provider LLM support (Anthropic, OpenAI, Ollama)
- Chain of Thought (CoT) reasoning with visualization
- Semantic memory search with pgvector
- Long-term fact extraction and storage
- Tenant-isolated conversations and memory
- Secure write operations with audit logging
"""

# Domain entities
from .domain.entities import (
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
    UserContext,
)

# Orchestrator
from .orchestrator import AgentOrchestrator, AgentConfig

# Memory
from .memory import (
    ConversationStore,
    SemanticMemoryStore,
    FactExtractor,
    EmbeddingWorker,
    EmbeddingWorkerPool,
)

# Tools
from .tools import (
    MCPClient,
    WriteExecutor,
    ToolRegistry,
)

# Providers
from .providers import (
    BaseLLMProvider,
    LLMProviderConfig,
    AnthropicProvider,
    OpenAIProvider,
    VoyageAIProvider,
)

# Security
from .security import (
    CoTRedactor,
    TicketAuth,
)

__all__ = [
    # Domain
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
    "UserContext",
    # Orchestrator
    "AgentOrchestrator",
    "AgentConfig",
    # Memory
    "ConversationStore",
    "SemanticMemoryStore",
    "FactExtractor",
    "EmbeddingWorker",
    "EmbeddingWorkerPool",
    # Tools
    "MCPClient",
    "WriteExecutor",
    "ToolRegistry",
    # Providers
    "BaseLLMProvider",
    "LLMProviderConfig",
    "AnthropicProvider",
    "OpenAIProvider",
    "VoyageAIProvider",
    # Security
    "CoTRedactor",
    "TicketAuth",
]
