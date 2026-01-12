"""
WebSocket Ticket Authentication.

Provides secure ticket-based authentication for WebSocket connections.
Tickets are:
- One-time use (consumed on validation)
- Short-lived (60 second TTL)
- Bound to user, tenant, and session

Security Principle: Never pass JWT in WebSocket URL query params.
Instead, use short-lived tickets that are consumed immediately.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Optional, Protocol


class IRedisClient(Protocol):
    """Protocol for Redis client (for dependency injection)."""

    async def setex(self, key: str, ttl: int, value: str) -> None:
        """Set a key with expiration."""
        ...

    async def get(self, key: str) -> Optional[str]:
        """Get a key value."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a key."""
        ...

    async def getdel(self, key: str) -> Optional[str]:
        """Get and delete a key atomically (Redis 6.2+)."""
        ...


@dataclass
class WebSocketTicket:
    """A WebSocket authentication ticket.

    Attributes:
        ticket: The ticket string (secret)
        user_id: User identifier
        tenant_id: Tenant identifier for isolation
        session_id: Session identifier for tracking
        conversation_id: Optional conversation to connect to
        created_at: Creation timestamp (for clock skew validation)
    """

    ticket: str
    user_id: str
    tenant_id: str
    session_id: str
    conversation_id: Optional[str] = None
    created_at: float = 0.0

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, data: str) -> WebSocketTicket:
        """Deserialize from JSON."""
        return cls(**json.loads(data))

    def is_expired(self, max_age_seconds: int = 120) -> bool:
        """Check if ticket is expired (with clock skew tolerance).

        Args:
            max_age_seconds: Maximum age in seconds (default 120 for clock skew)

        Returns:
            True if ticket is expired
        """
        return time.time() - self.created_at > max_age_seconds


class WebSocketTicketAuth:
    """WebSocket ticket authentication service.

    Usage:
        # Create ticket (in REST endpoint, before WS connection)
        auth = WebSocketTicketAuth(redis)
        ticket = await auth.create_ticket(user_id, tenant_id, session_id)

        # Validate ticket (in WebSocket handler)
        ticket_data = await auth.validate_ticket(ticket)
        if not ticket_data:
            await websocket.close(code=4001, reason="Invalid ticket")
    """

    # Redis key prefix
    KEY_PREFIX = "ws_ticket:"

    # Default TTL in seconds
    DEFAULT_TTL = 60

    # Maximum age for clock skew tolerance
    MAX_AGE = 120

    def __init__(self, redis: IRedisClient, ttl: int = DEFAULT_TTL):
        """Initialize ticket auth service.

        Args:
            redis: Redis client for ticket storage
            ttl: Ticket TTL in seconds (default 60)
        """
        self.redis = redis
        self.ttl = ttl

    async def create_ticket(
        self,
        user_id: str,
        tenant_id: str,
        session_id: str,
        conversation_id: Optional[str] = None,
    ) -> str:
        """Create a new WebSocket authentication ticket.

        Args:
            user_id: User identifier
            tenant_id: Tenant identifier
            session_id: Session identifier
            conversation_id: Optional conversation to connect to

        Returns:
            The ticket string to pass to WebSocket connection
        """
        # Generate secure random ticket
        ticket_str = secrets.token_urlsafe(32)

        # Create ticket data
        ticket = WebSocketTicket(
            ticket=ticket_str,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
            conversation_id=conversation_id,
        )

        # Store in Redis with TTL
        key = f"{self.KEY_PREFIX}{ticket_str}"
        await self.redis.setex(key, self.ttl, ticket.to_json())

        return ticket_str

    async def validate_ticket(self, ticket: str) -> Optional[WebSocketTicket]:
        """Validate and consume a ticket (one-time use).

        Args:
            ticket: The ticket string from WebSocket query param

        Returns:
            WebSocketTicket if valid, None if invalid/expired/consumed
        """
        if not ticket:
            return None

        key = f"{self.KEY_PREFIX}{ticket}"

        # Try atomic get-and-delete (Redis 6.2+)
        try:
            data = await self.redis.getdel(key)
        except AttributeError:
            # Fallback for older Redis: use Lua script for atomicity
            # This ensures the ticket can only be consumed once
            lua_script = """
            local value = redis.call('GET', KEYS[1])
            if value then
                redis.call('DEL', KEYS[1])
            end
            return value
            """
            try:
                # Try using eval for atomic get-and-delete
                data = await self.redis.eval(lua_script, 1, key)
            except (AttributeError, Exception):
                # Last resort fallback: get then delete (race condition possible)
                # Log warning as this is not atomic
                import logging
                logging.getLogger(__name__).warning(
                    "Using non-atomic ticket validation - upgrade Redis to 6.2+ for GETDEL"
                )
                data = await self.redis.get(key)
                if data:
                    await self.redis.delete(key)

        if not data:
            return None

        # Parse ticket data
        try:
            ticket_data = WebSocketTicket.from_json(data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

        # Verify ticket matches
        if ticket_data.ticket != ticket:
            return None

        # Check expiration with clock skew tolerance
        if ticket_data.is_expired(self.MAX_AGE):
            return None

        return ticket_data

    async def revoke_ticket(self, ticket: str) -> bool:
        """Revoke a ticket (e.g., on logout).

        Args:
            ticket: The ticket string to revoke

        Returns:
            True if ticket was revoked, False if not found
        """
        key = f"{self.KEY_PREFIX}{ticket}"
        data = await self.redis.get(key)
        if data:
            await self.redis.delete(key)
            return True
        return False
