"""Agent Orchestrator.

The orchestrator coordinates all components of the agent chatbot:
- LLM provider for response generation
- Tool registry for read/write operations
- Memory system for context and facts
- Streaming events for real-time UI updates

Provides:
- Main orchestrator and configuration
- Conversation history management
- Memory and semantic search
- Pattern learning and adaptation
- Tool execution with confirmations
- Event streaming for real-time UI
- Prompt building and context assembly
"""

from .agent import AgentOrchestrator, AgentConfig
from .conversation_manager import ConversationManager
from .memory_manager import MemoryManager
from .pattern_manager import PatternManager
from .tool_executor import ToolExecutor
from .event_streamer import EventStreamer
from .confirmation_manager import ConfirmationManager
from .prompt_builder import PromptBuilder

__all__ = [
    # Main orchestrator
    "AgentOrchestrator",
    "AgentConfig",
    # Core managers
    "ConversationManager",
    "MemoryManager",
    "PatternManager",
    "ToolExecutor",
    "EventStreamer",
    "ConfirmationManager",
    "PromptBuilder",
]
