"""
Conversation Manager.

Handles conversation lifecycle management including creation,
retrieval, history management, and message storage.

This module extracts conversation-related responsibilities from
the AgentOrchestrator to improve modularity and testability.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from ..domain.entities import Conversation, Message, UserContext
from ..domain.ports import IConversationStore

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation lifecycle operations.

    Provides a clean API for conversation management operations,
    abstracting the underlying conversation store implementation.

    Usage:
        manager = ConversationManager(conversation_store)

        # Get or create conversation
        conversation = await manager.get_or_create(
            conversation_id=None,
            context=user_context,
        )

        # Add a message
        await manager.add_message(
            conversation_id=conversation.id,
            message=user_message,
            context=user_context,
        )

        # Get conversation history
        history = await manager.get_history(
            conversation_id=conversation.id,
            context=user_context,
        )

        # List user conversations
        conversations = await manager.list_conversations(
            context=user_context,
            limit=20,
        )
    """

    def __init__(self, conversation_store: Optional[IConversationStore] = None):
        """Initialize the conversation manager.

        Args:
            conversation_store: Store for conversation persistence.
                               If None, operations will work in-memory only.
        """
        self.store = conversation_store

    async def get_or_create(
        self,
        conversation_id: Optional[UUID],
        context: UserContext,
    ) -> Conversation:
        """Get existing or create new conversation.

        If conversation_id is provided and exists, retrieves it.
        Otherwise, creates a new conversation.

        Args:
            conversation_id: Existing conversation ID or None
            context: User context for tenant isolation

        Returns:
            Conversation object (existing or newly created)
        """
        # Try to get existing conversation
        if conversation_id and self.store:
            conversation = await self.store.get(conversation_id, context)
            if conversation:
                logger.debug(
                    f"Retrieved existing conversation {conversation_id} "
                    f"for user {context.user_id}"
                )
                return conversation

        # Create new conversation
        conversation = Conversation(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
        )

        if self.store:
            conversation = await self.store.create(conversation)
            logger.info(
                f"Created new conversation {conversation.id} "
                f"for user {context.user_id}"
            )
        else:
            logger.warning(
                "No conversation store available - conversation will be in-memory only"
            )

        return conversation

    async def add_message(
        self,
        conversation_id: UUID,
        message: Message,
        context: UserContext,
    ) -> Message:
        """Add a message to a conversation.

        Stores the message in the conversation store and returns the
        stored message with any generated fields (ID, timestamp, etc.).

        Args:
            conversation_id: ID of the conversation
            message: Message to add
            context: User context for tenant isolation

        Returns:
            The stored message with generated fields
        """
        if not self.store:
            logger.warning(
                "No conversation store available - message will not be persisted"
            )
            return message

        stored_message = await self.store.add_message(
            conversation_id, message, context
        )

        logger.debug(
            f"Added {message.role} message to conversation {conversation_id}"
        )

        return stored_message

    async def get_history(
        self,
        conversation_id: UUID,
        context: UserContext,
        limit: int = 50,
    ) -> Optional[Conversation]:
        """Get conversation history with messages.

        Retrieves the conversation along with its messages.

        Args:
            conversation_id: ID of the conversation
            context: User context for tenant isolation
            limit: Maximum number of messages to return

        Returns:
            Conversation with messages, or None if not found
        """
        if not self.store:
            logger.warning("No conversation store available - cannot retrieve history")
            return None

        conversation = await self.store.get(conversation_id, context)

        if conversation:
            logger.debug(
                f"Retrieved conversation {conversation_id} with "
                f"{len(conversation.messages)} messages"
            )
        else:
            logger.warning(f"Conversation {conversation_id} not found")

        return conversation

    async def list_conversations(
        self,
        context: UserContext,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """List user's conversations.

        Retrieves a paginated list of conversations for the user.

        Args:
            context: User context for tenant isolation
            limit: Maximum number of conversations to return
            offset: Pagination offset

        Returns:
            List of conversations (may be empty)
        """
        if not self.store:
            logger.warning("No conversation store available - returning empty list")
            return []

        conversations = await self.store.list(context, limit, offset)

        logger.debug(
            f"Listed {len(conversations)} conversations for user {context.user_id}"
        )

        return conversations
