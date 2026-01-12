"""
Conversation Store Implementation.

Handles conversation and message persistence with tenant isolation.
Uses PostgreSQL with RLS for security.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional, Protocol
from uuid import UUID

from ..domain.entities import (
    Conversation,
    Message,
    MessageRole,
    ToolCall,
    UserContext,
)
from ..domain.ports import IConversationStore

logger = logging.getLogger(__name__)


class IAsyncDBPool(Protocol):
    """Protocol for async database pool."""

    async def acquire(self): ...
    async def execute(self, query: str, *args) -> str: ...
    async def fetch(self, query: str, *args) -> list[Any]: ...
    async def fetchrow(self, query: str, *args) -> Optional[Any]: ...
    async def fetchval(self, query: str, *args) -> Any: ...


class ConversationStore(IConversationStore):
    """PostgreSQL-based conversation store with tenant isolation.

    Uses RLS policies for tenant isolation. All queries automatically
    filter by tenant_id via the app.tenant_id session variable.

    Usage:
        store = ConversationStore(db_pool)

        # Create conversation
        conv = await store.create(Conversation(
            tenant_id="tenant-123",
            user_id="user-456",
            title="Device Search",
        ))

        # Add message
        msg = await store.add_message(
            conv.id,
            Message(role=MessageRole.USER, content="Find all switches"),
            context,
        )

        # Get conversation with messages
        conv = await store.get(conv.id, context)
    """

    def __init__(self, db_pool: IAsyncDBPool):
        """Initialize the conversation store.

        Args:
            db_pool: Async database connection pool
        """
        self.db = db_pool

    async def _set_tenant_context(self, conn, tenant_id: str) -> None:
        """Set the tenant context for RLS policies."""
        await conn.execute(
            "SET LOCAL app.tenant_id = $1",
            tenant_id,
        )

    async def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation.

        Args:
            conversation: Conversation to create

        Returns:
            Created conversation with ID
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, conversation.tenant_id)

                row = await conn.fetchrow(
                    """
                    INSERT INTO agent_conversations (
                        id, tenant_id, user_id, title, summary, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id, created_at, updated_at
                    """,
                    conversation.id,
                    conversation.tenant_id,
                    conversation.user_id,
                    conversation.title,
                    conversation.summary,
                    conversation.metadata,
                )

                conversation.created_at = row["created_at"]
                conversation.updated_at = row["updated_at"]

        logger.info(
            f"Created conversation {conversation.id} for user {conversation.user_id}"
        )
        return conversation

    async def get(
        self, conversation_id: UUID, context: UserContext
    ) -> Optional[Conversation]:
        """Get a conversation by ID with messages.

        Args:
            conversation_id: Conversation ID
            context: User context for tenant isolation

        Returns:
            Conversation with messages, or None if not found
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, context.tenant_id)

                # Get conversation
                row = await conn.fetchrow(
                    """
                    SELECT id, tenant_id, user_id, title, summary,
                           message_count, metadata, created_at, updated_at
                    FROM agent_conversations
                    WHERE id = $1 AND user_id = $2
                    """,
                    conversation_id,
                    context.user_id,
                )

                if not row:
                    return None

                conversation = Conversation(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    title=row["title"],
                    summary=row["summary"],
                    message_count=row["message_count"],
                    metadata=row["metadata"] or {},
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

                # Get messages
                message_rows = await conn.fetch(
                    """
                    SELECT id, role, content, thinking_summary, tool_calls,
                           model_used, tokens_used, latency_ms, created_at
                    FROM agent_messages
                    WHERE conversation_id = $1
                    ORDER BY created_at ASC
                    """,
                    conversation_id,
                )

                for msg_row in message_rows:
                    tool_calls = None
                    if msg_row["tool_calls"]:
                        tool_calls = [
                            ToolCall(
                                id=tc.get("id", ""),
                                name=tc.get("name", ""),
                                arguments=tc.get("arguments", {}),
                                result=tc.get("result"),
                            )
                            for tc in msg_row["tool_calls"]
                        ]

                    message = Message(
                        id=msg_row["id"],
                        conversation_id=conversation_id,
                        role=MessageRole(msg_row["role"]),
                        content=msg_row["content"],
                        thinking_summary=msg_row["thinking_summary"],
                        tool_calls=tool_calls,
                        model_used=msg_row["model_used"],
                        tokens_used=msg_row["tokens_used"],
                        latency_ms=msg_row["latency_ms"],
                        created_at=msg_row["created_at"],
                    )
                    conversation.messages.append(message)

        return conversation

    async def list(
        self,
        context: UserContext,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Conversation]:
        """List conversations for a user.

        Args:
            context: User context for tenant isolation
            limit: Maximum conversations to return
            offset: Pagination offset

        Returns:
            List of conversations (without full message history)
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, context.tenant_id)

                rows = await conn.fetch(
                    """
                    SELECT c.id, c.tenant_id, c.user_id, c.title, c.summary,
                           c.message_count, c.metadata, c.created_at, c.updated_at,
                           (SELECT content FROM agent_messages m
                            WHERE m.conversation_id = c.id
                            ORDER BY m.created_at DESC LIMIT 1) as last_message
                    FROM agent_conversations c
                    WHERE c.user_id = $1
                    ORDER BY c.updated_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    context.user_id,
                    limit,
                    offset,
                )

                conversations = []
                for row in rows:
                    conv = Conversation(
                        id=row["id"],
                        tenant_id=row["tenant_id"],
                        user_id=row["user_id"],
                        title=row["title"],
                        summary=row["summary"],
                        message_count=row["message_count"],
                        metadata=row["metadata"] or {},
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    # Add last message preview to metadata
                    if row["last_message"]:
                        conv.metadata["last_message_preview"] = row["last_message"][:100]
                    conversations.append(conv)

        return conversations

    async def add_message(
        self, conversation_id: UUID, message: Message, context: UserContext
    ) -> Message:
        """Add a message to a conversation.

        Args:
            conversation_id: Conversation ID
            message: Message to add
            context: User context for tenant isolation

        Returns:
            Created message with ID and timestamp
        """
        message.conversation_id = conversation_id

        # Serialize tool calls if present
        tool_calls_json = None
        if message.tool_calls:
            tool_calls_json = [
                {
                    "id": tc.id,
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": tc.result,
                }
                for tc in message.tool_calls
            ]

        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, context.tenant_id)

                # Verify conversation exists and belongs to user
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM agent_conversations
                    WHERE id = $1 AND user_id = $2
                    """,
                    conversation_id,
                    context.user_id,
                )

                if not exists:
                    raise ValueError(
                        f"Conversation {conversation_id} not found or access denied"
                    )

                row = await conn.fetchrow(
                    """
                    INSERT INTO agent_messages (
                        id, conversation_id, tenant_id, role, content, thinking_summary,
                        tool_calls, model_used, tokens_used, latency_ms
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id, created_at
                    """,
                    message.id,
                    conversation_id,
                    context.tenant_id,  # Include tenant_id for RLS
                    message.role.value,
                    message.content,
                    message.thinking_summary,
                    tool_calls_json,
                    message.model_used,
                    message.tokens_used,
                    message.latency_ms,
                )

                message.created_at = row["created_at"]

        logger.debug(
            f"Added {message.role.value} message to conversation {conversation_id}"
        )
        return message

    async def get_messages(
        self,
        conversation_id: UUID,
        context: UserContext,
        limit: int = 50,
        before: Optional[UUID] = None,
    ) -> list[Message]:
        """Get messages from a conversation.

        Args:
            conversation_id: Conversation ID
            context: User context
            limit: Maximum messages to return
            before: Get messages before this message ID (for pagination)

        Returns:
            List of messages ordered by creation time
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, context.tenant_id)

                # Verify access
                exists = await conn.fetchval(
                    """
                    SELECT 1 FROM agent_conversations
                    WHERE id = $1 AND user_id = $2
                    """,
                    conversation_id,
                    context.user_id,
                )

                if not exists:
                    raise ValueError(
                        f"Conversation {conversation_id} not found or access denied"
                    )

                if before:
                    rows = await conn.fetch(
                        """
                        SELECT id, role, content, thinking_summary, tool_calls,
                               model_used, tokens_used, latency_ms, created_at
                        FROM agent_messages
                        WHERE conversation_id = $1
                          AND created_at < (SELECT created_at FROM agent_messages WHERE id = $2)
                        ORDER BY created_at DESC
                        LIMIT $3
                        """,
                        conversation_id,
                        before,
                        limit,
                    )
                    # Reverse to get chronological order
                    rows = list(reversed(rows))
                else:
                    rows = await conn.fetch(
                        """
                        SELECT id, role, content, thinking_summary, tool_calls,
                               model_used, tokens_used, latency_ms, created_at
                        FROM agent_messages
                        WHERE conversation_id = $1
                        ORDER BY created_at ASC
                        LIMIT $2
                        """,
                        conversation_id,
                        limit,
                    )

                messages = []
                for row in rows:
                    tool_calls = None
                    if row["tool_calls"]:
                        tool_calls = [
                            ToolCall(
                                id=tc.get("id", ""),
                                name=tc.get("name", ""),
                                arguments=tc.get("arguments", {}),
                                result=tc.get("result"),
                            )
                            for tc in row["tool_calls"]
                        ]

                    messages.append(Message(
                        id=row["id"],
                        conversation_id=conversation_id,
                        role=MessageRole(row["role"]),
                        content=row["content"],
                        thinking_summary=row["thinking_summary"],
                        tool_calls=tool_calls,
                        model_used=row["model_used"],
                        tokens_used=row["tokens_used"],
                        latency_ms=row["latency_ms"],
                        created_at=row["created_at"],
                    ))

        return messages

    async def update_summary(
        self, conversation_id: UUID, summary: str, context: UserContext
    ) -> None:
        """Update the conversation summary.

        Args:
            conversation_id: Conversation ID
            summary: New summary text
            context: User context
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, context.tenant_id)

                result = await conn.execute(
                    """
                    UPDATE agent_conversations
                    SET summary = $1, updated_at = NOW()
                    WHERE id = $2 AND user_id = $3
                    """,
                    summary,
                    conversation_id,
                    context.user_id,
                )

                if result == "UPDATE 0":
                    raise ValueError(
                        f"Conversation {conversation_id} not found or access denied"
                    )

        logger.debug(f"Updated summary for conversation {conversation_id}")

    async def update_title(
        self, conversation_id: UUID, title: str, context: UserContext
    ) -> None:
        """Update the conversation title.

        Args:
            conversation_id: Conversation ID
            title: New title
            context: User context
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, context.tenant_id)

                result = await conn.execute(
                    """
                    UPDATE agent_conversations
                    SET title = $1, updated_at = NOW()
                    WHERE id = $2 AND user_id = $3
                    """,
                    title,
                    conversation_id,
                    context.user_id,
                )

                if result == "UPDATE 0":
                    raise ValueError(
                        f"Conversation {conversation_id} not found or access denied"
                    )

    async def delete(self, conversation_id: UUID, context: UserContext) -> bool:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: Conversation ID
            context: User context

        Returns:
            True if deleted, False if not found
        """
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await self._set_tenant_context(conn, context.tenant_id)

                result = await conn.execute(
                    """
                    DELETE FROM agent_conversations
                    WHERE id = $1 AND user_id = $2
                    """,
                    conversation_id,
                    context.user_id,
                )

                deleted = result == "DELETE 1"

        if deleted:
            logger.info(f"Deleted conversation {conversation_id}")
        return deleted

    async def get_recent_context(
        self,
        conversation_id: UUID,
        context: UserContext,
        max_messages: int = 10,
        max_tokens: int = 4000,
    ) -> list[Message]:
        """Get recent messages for context window.

        Retrieves the most recent messages that fit within token budget.
        Useful for building LLM context.

        Args:
            conversation_id: Conversation ID
            context: User context
            max_messages: Maximum messages to include
            max_tokens: Approximate token budget

        Returns:
            List of recent messages
        """
        messages = await self.get_messages(
            conversation_id,
            context,
            limit=max_messages * 2,  # Fetch extra to filter by tokens
        )

        # Simple token estimation (rough: 4 chars = 1 token)
        result = []
        total_tokens = 0

        for msg in reversed(messages):
            estimated_tokens = len(msg.content) // 4
            if total_tokens + estimated_tokens > max_tokens:
                break
            result.insert(0, msg)
            total_tokens += estimated_tokens

            if len(result) >= max_messages:
                break

        return result
