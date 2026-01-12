"""Memory system for the agent chatbot.

Provides:
- Semantic memory search with pgvector
- Long-term fact extraction and storage
- Conversation history management
- Background embedding generation
- AgentDB memory patterns (sessions, patterns, versioning)
"""

from .conversation import ConversationStore
from .semantic import SemanticMemoryStore
from .long_term import FactExtractor, ExtractedFact, ConversationSummarizer
from .embedding_worker import EmbeddingWorker, EmbeddingWorkerPool
from .agentdb import (
    AgentDBAdapter,
    PersistentSessionStore,
    PatternLearningStore,
    MemoryVersioningStore,
    SessionType,
    PatternType,
    MemoryVersion,
    SessionData,
    LearnedPattern,
    MemoryRevision,
)

__all__ = [
    # Core memory components
    "ConversationStore",
    "SemanticMemoryStore",
    "FactExtractor",
    "ExtractedFact",
    "ConversationSummarizer",
    "EmbeddingWorker",
    "EmbeddingWorkerPool",
    # AgentDB memory patterns
    "AgentDBAdapter",
    "PersistentSessionStore",
    "PatternLearningStore",
    "MemoryVersioningStore",
    "SessionType",
    "PatternType",
    "MemoryVersion",
    "SessionData",
    "LearnedPattern",
    "MemoryRevision",
]
