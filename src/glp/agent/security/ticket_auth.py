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

    async def eval(self, script: str, numkeys: int, *keys_and_args) -> Optional[str]:
        """Execute a Lua script atomically."""
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

    # Lua script for atomic get-and-delete (used as fallback for Redis < 6.2)
    # This ensures the ticket can only be consumed once, preventing race conditions
    _ATOMIC_GETDEL_SCRIPT = """
    local value = redis.call('GET', KEYS[1])
    if value then
        redis.call('DEL', KEYS[1])
    end
    return value
    """

    async def validate_ticket(self, ticket: str) -> Optional[WebSocketTicket]:
        """Validate and consume a ticket (one-time use).

        Uses atomic operations to prevent race conditions where two concurrent
        requests could both validate the same ticket.

        Args:
            ticket: The ticket string from WebSocket query param

        Returns:
            WebSocketTicket if valid, None if invalid/expired/consumed
        """
        if not ticket:
            return None

        key = f"{self.KEY_PREFIX}{ticket}"
        data: Optional[str] = None

        # Strategy 1: Try GETDEL (Redis 6.2+) - most efficient
        try:
            data = await self.redis.getdel(key)
        except (AttributeError, Exception):
            pass

        # Strategy 2: Fall back to Lua script for atomicity (Redis 2.6+)
        # This is the critical fix - NEVER use non-atomic get+delete
        if data is None:
            try:
                data = await self.redis.eval(self._ATOMIC_GETDEL_SCRIPT, 1, key)
            except (AttributeError, Exception) as e:
                # If neither GETDEL nor EVAL work, the Redis client is incompatible
                # Fail closed - do NOT fall back to non-atomic operations
                import logging
                logging.getLogger(__name__).error(
                    f"Redis client does not support GETDEL or EVAL - "
                    f"ticket validation unavailable: {e}"
                )
                return None

        if not data:
            return None

        # Parse ticket data
        try:
            ticket_data = WebSocketTicket.from_json(data)
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

        # Verify ticket matches (defense in depth)
        if not secrets.compare_digest(ticket_data.ticket, ticket):
            return None

        # Check expiration with clock skew tolerance
        if ticket_data.is_expired(self.MAX_AGE):
            return None

        return ticket_data

    async def revoke_ticket(self, ticket: str) -> bool:
        """Revoke a ticket atomically (e.g., on logout).

        Uses atomic operations to ensure ticket is deleted exactly once,
        preventing race conditions.

        Args:
            ticket: The ticket string to revoke

        Returns:
            True if ticket was revoked, False if not found
        """
        if not ticket:
            return False

        key = f"{self.KEY_PREFIX}{ticket}"

        # Strategy 1: Try GETDEL (Redis 6.2+) - atomic
        try:
            data = await self.redis.getdel(key)
            return data is not None
        except (AttributeError, Exception):
            pass

        # Strategy 2: Fall back to Lua script for atomicity
        try:
            data = await self.redis.eval(self._ATOMIC_GETDEL_SCRIPT, 1, key)
            return data is not None
        except (AttributeError, Exception):
            pass

        # If neither atomic method works, use delete directly
        # (delete returns the number of keys deleted in most clients)
        try:
            await self.redis.delete(key)
            return True  # Assume success - delete is idempotent
        except Exception:
            return False
