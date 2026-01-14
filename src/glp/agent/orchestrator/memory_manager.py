"""
Memory Manager for Agent Orchestrator.

Encapsulates memory-related operations:
- Semantic memory search and retrieval
- Fact extraction coordination
- Memory storage orchestration
- Context building from memories

Extracted from AgentOrchestrator to improve modularity and testability.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from ..domain.entities import Memory, MemoryType, UserContext
from ..domain.ports import IMemoryStore
from ..memory.long_term import FactExtractor

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages semantic memory operations for the agent.

    Responsibilities:
    - Search memory for relevant context based on queries
    - Extract facts from conversation content
    - Store memories with proper metadata
    - Build context strings for system prompts

    Usage:
        memory_manager = MemoryManager(
            memory_store=semantic_store,
            fact_extractor=extractor,
            search_limit=5,
            min_confidence=0.5,
        )

        # Search for relevant context
        memories = await memory_manager.search_memory(
            query="What region does user prefer?",
            context=user_context,
            embedding_model="text-embedding-3-large",
        )

        # Extract and store facts from response
        await memory_manager.extract_and_store_facts(
            content=response_text,
            conversation_id=conv_id,
            message_id=msg_id,
            context=user_context,
        )
    """

    def __init__(
        self,
        memory_store: Optional[IMemoryStore] = None,
        fact_extractor: Optional[FactExtractor] = None,
        search_limit: int = 5,
        min_confidence: float = 0.5,
        enable_search: bool = True,
        enable_extraction: bool = True,
    ):
        """Initialize the memory manager.

        Args:
            memory_store: Store for semantic memory operations
            fact_extractor: Extractor for long-term facts
            search_limit: Maximum memories to retrieve per search
            min_confidence: Minimum confidence threshold for results
            enable_search: Whether memory search is enabled
            enable_extraction: Whether fact extraction is enabled
        """
        self.memory_store = memory_store
        self.fact_extractor = fact_extractor
        self.search_limit = search_limit
        self.min_confidence = min_confidence
        self.enable_search = enable_search
        self.enable_extraction = enable_extraction

    async def search_memory(
        self,
        query: str,
        context: UserContext,
        embedding_model: str,
        memory_types: Optional[list[MemoryType]] = None,
    ) -> list[Memory]:
        """Search memory for relevant context.

        Args:
            query: Search query text
            context: User context for tenant isolation
            embedding_model: Model name for embedding search
            memory_types: Optional filter by memory types

        Returns:
            List of relevant memories sorted by relevance
        """
        if not self.enable_search or not self.memory_store:
            logger.debug("Memory search disabled or no store available")
            return []

        try:
            results = await self.memory_store.search(
                query=query,
                context=context,
                embedding_model=embedding_model,
                limit=self.search_limit,
                memory_types=memory_types,
                min_confidence=self.min_confidence,
            )
            memories = [memory for memory, _ in results]
            logger.debug(f"Found {len(memories)} relevant memories for query: {query[:50]}...")
            return memories

        except Exception as e:
            logger.warning(f"Memory search failed: {e}")
            return []

    async def extract_and_store_facts(
        self,
        content: str,
        conversation_id: UUID,
        message_id: UUID,
        context: UserContext,
    ) -> int:
        """Extract facts from content and store in memory.

        Args:
            content: Text to extract facts from
            conversation_id: Source conversation ID
            message_id: Source message ID
            context: User context

        Returns:
            Number of facts extracted and stored
        """
        if not self.enable_extraction or not self.fact_extractor or not self.memory_store:
            logger.debug("Fact extraction disabled or dependencies unavailable")
            return 0

        try:
            # Extract facts using LLM
            facts = await self.fact_extractor.extract(content)

            # Convert to memories and store
            stored_count = 0
            for fact in facts:
                memory = fact.to_memory(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    source_conversation_id=conversation_id,
                    source_message_id=message_id,
                )
                await self.memory_store.store(memory)
                stored_count += 1

            if stored_count > 0:
                logger.info(f"Extracted and stored {stored_count} facts")

            return stored_count

        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")
            return 0

    async def store_memory(
        self,
        memory: Memory,
    ) -> Optional[Memory]:
        """Store a single memory.

        Args:
            memory: Memory to store

        Returns:
            Stored memory with updated metadata, or None if failed
        """
        if not self.memory_store:
            logger.debug("No memory store available")
            return None

        try:
            stored = await self.memory_store.store(memory)
            logger.debug(f"Stored memory {stored.id}: {stored.content[:50]}...")
            return stored

        except Exception as e:
            logger.warning(f"Memory storage failed: {e}")
            return None

    def build_memory_context(
        self,
        memories: list[Memory],
    ) -> str:
        """Build context string from memories for system prompt.

        Args:
            memories: List of relevant memories

        Returns:
            Formatted context string
        """
        if not memories:
            return ""

        context = "\n\nRelevant context from previous conversations:\n"
        for mem in memories:
            context += f"- [{mem.memory_type.value}] {mem.content}\n"

        return context

    async def get_memory_by_id(
        self,
        memory_id: UUID,
        context: UserContext,
    ) -> Optional[Memory]:
        """Get a specific memory by ID.

        Args:
            memory_id: Memory identifier
            context: User context for access control

        Returns:
            Memory if found and accessible, None otherwise
        """
        if not self.memory_store:
            return None

        try:
            return await self.memory_store.get(memory_id, context)
        except Exception as e:
            logger.warning(f"Failed to retrieve memory {memory_id}: {e}")
            return None

    async def invalidate_memory(
        self,
        memory_id: UUID,
        context: UserContext,
    ) -> bool:
        """Soft-delete a memory.

        Args:
            memory_id: Memory to invalidate
            context: User context for access control

        Returns:
            True if invalidated, False otherwise
        """
        if not self.memory_store:
            return False

        try:
            return await self.memory_store.invalidate(memory_id, context)
        except Exception as e:
            logger.warning(f"Failed to invalidate memory {memory_id}: {e}")
            return False

    async def get_memories_by_source(
        self,
        conversation_id: Optional[UUID],
        message_id: Optional[UUID],
        context: UserContext,
    ) -> list[Memory]:
        """Get memories extracted from a specific source.

        Args:
            conversation_id: Filter by source conversation
            message_id: Filter by source message
            context: User context

        Returns:
            List of memories from the specified source
        """
        if not self.memory_store:
            return []

        try:
            return await self.memory_store.get_by_source(
                conversation_id=conversation_id,
                message_id=message_id,
                context=context,
            )
        except Exception as e:
            logger.warning(f"Failed to get memories by source: {e}")
            return []

    async def get_memory_stats(
        self,
        context: UserContext,
    ) -> dict:
        """Get memory statistics for a user.

        Args:
            context: User context

        Returns:
            Statistics dict with counts by type, avg confidence, etc.
        """
        if not self.memory_store:
            return {
                "by_type": {},
                "total": 0,
                "active": 0,
            }

        try:
            return await self.memory_store.get_stats(context)
        except Exception as e:
            logger.warning(f"Failed to get memory stats: {e}")
            return {
                "by_type": {},
                "total": 0,
                "active": 0,
            }
