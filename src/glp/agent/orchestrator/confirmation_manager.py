"""
Confirmation Manager.

Manages pending operation confirmations with support for:
- Persistent storage via AgentDB (survives server restarts)
- In-memory fallback (when AgentDB not available)
- TTL-based expiration
- Multi-conversation isolation
- Atomic get-and-delete operations

This module abstracts the confirmation storage logic from the main
orchestrator, providing a clean interface for managing user confirmations.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from ..domain.entities import UserContext
from ..memory.agentdb import AgentDBAdapter, SessionType

logger = logging.getLogger(__name__)


class ConfirmationManager:
    """Manages pending operation confirmations.

    Provides a unified interface for storing, retrieving, and deleting
    pending confirmations. Supports both persistent (AgentDB-backed) and
    in-memory storage.

    Features:
    - Stores confirmation data with TTL
    - Atomic get-and-delete for single-use confirmations
    - Lists all confirmations for a conversation
    - Cleans up all confirmations for a conversation

    Usage:
        manager = ConfirmationManager(agentdb=agentdb, ttl_seconds=3600)

        # Store a confirmation
        await manager.store(
            context=user_context,
            conversation_id=conv_id,
            operation_id="op-123",
            confirmation_data={"tool_call": {...}},
        )

        # Retrieve and delete a specific confirmation
        data = await manager.get_and_delete(
            context=user_context,
            conversation_id=conv_id,
            operation_id="op-123",
        )

        # Get first available confirmation (backward compatibility)
        data = await manager.get_and_delete(
            context=user_context,
            conversation_id=conv_id,
        )

        # Clean up all confirmations for a conversation
        await manager.cleanup_conversation(
            context=user_context,
            conversation_id=conv_id,
        )
    """

    def __init__(
        self,
        agentdb: Optional[AgentDBAdapter] = None,
        ttl_seconds: int = 3600,
    ):
        """Initialize the confirmation manager.

        Args:
            agentdb: Optional AgentDB adapter for persistent storage
            ttl_seconds: TTL for confirmations (default: 1 hour)
        """
        self.agentdb = agentdb
        self.ttl_seconds = ttl_seconds

        # Fallback in-memory store when AgentDB not available
        # Structure: {conversation_id: {operation_id: {...}}}
        self._pending_confirmations: dict[UUID, dict[str, dict[str, Any]]] = {}

    async def store(
        self,
        context: UserContext,
        conversation_id: UUID,
        operation_id: str,
        confirmation_data: dict[str, Any],
    ) -> None:
        """Store a pending confirmation.

        Args:
            context: User context
            conversation_id: Conversation identifier
            operation_id: Unique operation identifier
            confirmation_data: Confirmation details (operation_id, tool_call, etc.)
        """
        if self.agentdb:
            # Use persistent storage
            session_key = f"{conversation_id}:{operation_id}"
            await self.agentdb.sessions.set(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                session_type=SessionType.CONFIRMATION,
                key=session_key,
                data=confirmation_data,
                ttl_seconds=self.ttl_seconds,
            )
            logger.debug(f"Stored confirmation in AgentDB: {session_key}")
        else:
            # Use in-memory fallback
            if conversation_id not in self._pending_confirmations:
                self._pending_confirmations[conversation_id] = {}
            self._pending_confirmations[conversation_id][operation_id] = confirmation_data
            logger.debug(f"Stored confirmation in memory: {conversation_id}:{operation_id}")

    async def get_and_delete(
        self,
        context: UserContext,
        conversation_id: UUID,
        operation_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Retrieve and delete a pending confirmation.

        Atomically retrieves and removes a confirmation. If operation_id is
        provided, retrieves that specific confirmation. Otherwise, retrieves
        the first available confirmation for backward compatibility.

        Args:
            context: User context
            conversation_id: Conversation identifier
            operation_id: Optional operation identifier (gets first if None)

        Returns:
            Confirmation data if found, None otherwise
        """
        pending: Optional[dict[str, Any]] = None

        if self.agentdb:
            # Try persistent storage first
            if operation_id:
                # Get specific operation
                session_key = f"{conversation_id}:{operation_id}"
                session = await self.agentdb.sessions.get_and_delete(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    session_type=SessionType.CONFIRMATION,
                    key=session_key,
                )
                if session:
                    pending = session.data
                    logger.debug(f"Retrieved confirmation from AgentDB: {session_key}")
            else:
                # Get first available confirmation
                sessions = await self.agentdb.sessions.list_by_type(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    session_type=SessionType.CONFIRMATION,
                    prefix=f"{conversation_id}:",
                )
                if sessions:
                    first_session = sessions[0]
                    session = await self.agentdb.sessions.get_and_delete(
                        tenant_id=context.tenant_id,
                        user_id=context.user_id,
                        session_type=SessionType.CONFIRMATION,
                        key=first_session.key,
                    )
                    if session:
                        pending = session.data
                        logger.debug(f"Retrieved first confirmation from AgentDB: {first_session.key}")

        # Fallback to in-memory store if not found in AgentDB
        if not pending:
            conv_confirmations = self._pending_confirmations.get(conversation_id, {})

            if operation_id and operation_id in conv_confirmations:
                # Get specific operation
                pending = conv_confirmations.pop(operation_id)
                logger.debug(f"Retrieved confirmation from memory: {conversation_id}:{operation_id}")
            elif conv_confirmations:
                # Get first available confirmation (backward compatibility)
                first_op_id = next(iter(conv_confirmations))
                pending = conv_confirmations.pop(first_op_id)
                logger.debug(f"Retrieved first confirmation from memory: {conversation_id}:{first_op_id}")

            # Clean up empty conversation entry
            if not conv_confirmations:
                self._pending_confirmations.pop(conversation_id, None)

        return pending

    async def list_confirmations(
        self,
        context: UserContext,
        conversation_id: UUID,
    ) -> list[dict[str, Any]]:
        """List all pending confirmations for a conversation.

        Args:
            context: User context
            conversation_id: Conversation identifier

        Returns:
            List of confirmation data dictionaries
        """
        confirmations: list[dict[str, Any]] = []

        if self.agentdb:
            # Get from persistent storage
            sessions = await self.agentdb.sessions.list_by_type(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                session_type=SessionType.CONFIRMATION,
                prefix=f"{conversation_id}:",
            )
            confirmations.extend([session.data for session in sessions])
            logger.debug(f"Listed {len(sessions)} confirmations from AgentDB for {conversation_id}")

        # Also check in-memory store
        if conversation_id in self._pending_confirmations:
            mem_confirmations = list(self._pending_confirmations[conversation_id].values())
            confirmations.extend(mem_confirmations)
            logger.debug(f"Listed {len(mem_confirmations)} confirmations from memory for {conversation_id}")

        return confirmations

    async def cleanup_conversation(
        self,
        context: UserContext,
        conversation_id: UUID,
    ) -> int:
        """Clean up all confirmations for a conversation.

        Used when cancelling a conversation or cleaning up after completion.

        Args:
            context: User context
            conversation_id: Conversation identifier

        Returns:
            Number of confirmations cleaned up
        """
        count = 0

        # Clean up AgentDB sessions
        if self.agentdb:
            sessions = await self.agentdb.sessions.list_by_type(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                session_type=SessionType.CONFIRMATION,
                prefix=f"{conversation_id}:",
            )
            for session in sessions:
                await self.agentdb.sessions.delete(
                    tenant_id=context.tenant_id,
                    user_id=context.user_id,
                    session_type=SessionType.CONFIRMATION,
                    key=session.key,
                )
            count += len(sessions)
            logger.debug(f"Cleaned up {len(sessions)} AgentDB confirmations for {conversation_id}")

        # Clean up in-memory store
        if conversation_id in self._pending_confirmations:
            mem_count = len(self._pending_confirmations[conversation_id])
            self._pending_confirmations.pop(conversation_id, None)
            count += mem_count
            logger.debug(f"Cleaned up {mem_count} in-memory confirmations for {conversation_id}")

        logger.info(f"Cleaned up {count} total confirmations for conversation {conversation_id}")
        return count

    async def has_pending_confirmations(
        self,
        context: UserContext,
        conversation_id: UUID,
    ) -> bool:
        """Check if there are any pending confirmations for a conversation.

        Args:
            context: User context
            conversation_id: Conversation identifier

        Returns:
            True if there are pending confirmations
        """
        # Check AgentDB
        if self.agentdb:
            sessions = await self.agentdb.sessions.list_by_type(
                tenant_id=context.tenant_id,
                user_id=context.user_id,
                session_type=SessionType.CONFIRMATION,
                prefix=f"{conversation_id}:",
            )
            if sessions:
                return True

        # Check in-memory store
        return conversation_id in self._pending_confirmations and bool(
            self._pending_confirmations[conversation_id]
        )
