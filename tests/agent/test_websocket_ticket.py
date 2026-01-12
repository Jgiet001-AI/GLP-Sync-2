"""
Tests for WebSocket ticket authentication.

Ensures tickets are properly validated, consumed, and cannot be reused.
"""

import json
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.glp.agent.security.ticket_auth import (
    WebSocketTicket,
    WebSocketTicketAuth,
)


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        """Set a key with expiration."""
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        """Get a key value."""
        return self.store.get(key)

    async def delete(self, key: str) -> None:
        """Delete a key."""
        self.store.pop(key, None)

    async def getdel(self, key: str) -> str | None:
        """Get and delete a key atomically."""
        return self.store.pop(key, None)


@pytest.fixture
def redis():
    """Create a mock Redis client."""
    return MockRedis()


@pytest.fixture
def ticket_auth(redis):
    """Create a WebSocketTicketAuth instance."""
    return WebSocketTicketAuth(redis)


class TestTicketCreation:
    """Tests for ticket creation."""

    @pytest.mark.asyncio
    async def test_create_ticket_returns_string(self, ticket_auth):
        """Creating a ticket returns a string."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        assert isinstance(ticket, str)
        assert len(ticket) > 20  # Should be sufficiently long

    @pytest.mark.asyncio
    async def test_create_ticket_stores_in_redis(self, ticket_auth, redis):
        """Ticket data is stored in Redis."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        key = f"ws_ticket:{ticket}"
        assert key in redis.store

    @pytest.mark.asyncio
    async def test_create_ticket_includes_conversation_id(self, ticket_auth, redis):
        """Conversation ID is included if provided."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
            conversation_id="conv123",
        )
        key = f"ws_ticket:{ticket}"
        data = json.loads(redis.store[key])
        assert data["conversation_id"] == "conv123"

    @pytest.mark.asyncio
    async def test_create_ticket_unique(self, ticket_auth):
        """Each created ticket is unique."""
        tickets = set()
        for _ in range(100):
            ticket = await ticket_auth.create_ticket(
                user_id="user123",
                tenant_id="tenant456",
                session_id="session789",
            )
            assert ticket not in tickets
            tickets.add(ticket)


class TestTicketValidation:
    """Tests for ticket validation."""

    @pytest.mark.asyncio
    async def test_validate_valid_ticket(self, ticket_auth):
        """Valid ticket is validated successfully."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        result = await ticket_auth.validate_ticket(ticket)

        assert result is not None
        assert result.user_id == "user123"
        assert result.tenant_id == "tenant456"
        assert result.session_id == "session789"

    @pytest.mark.asyncio
    async def test_validate_invalid_ticket(self, ticket_auth):
        """Invalid ticket returns None."""
        result = await ticket_auth.validate_ticket("invalid-ticket")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_empty_ticket(self, ticket_auth):
        """Empty ticket returns None."""
        result = await ticket_auth.validate_ticket("")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_none_ticket(self, ticket_auth):
        """None ticket returns None."""
        result = await ticket_auth.validate_ticket(None)
        assert result is None


class TestTicketConsumption:
    """Tests for one-time ticket consumption."""

    @pytest.mark.asyncio
    async def test_ticket_consumed_after_validation(self, ticket_auth):
        """Ticket is deleted after successful validation."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        # First validation succeeds
        result1 = await ticket_auth.validate_ticket(ticket)
        assert result1 is not None

        # Second validation fails (ticket consumed)
        result2 = await ticket_auth.validate_ticket(ticket)
        assert result2 is None

    @pytest.mark.asyncio
    async def test_ticket_cannot_be_reused(self, ticket_auth):
        """Ticket cannot be reused after consumption."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        # Use the ticket
        await ticket_auth.validate_ticket(ticket)

        # Try 10 more times - all should fail
        for _ in range(10):
            result = await ticket_auth.validate_ticket(ticket)
            assert result is None


class TestTicketExpiration:
    """Tests for ticket expiration."""

    @pytest.mark.asyncio
    async def test_expired_ticket_rejected(self, ticket_auth, redis):
        """Expired ticket is rejected."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        # Manually modify the ticket data to make it expired
        key = f"ws_ticket:{ticket}"
        data = json.loads(redis.store[key])
        data["created_at"] = time.time() - 200  # 200 seconds ago (beyond max age)
        redis.store[key] = json.dumps(data)

        result = await ticket_auth.validate_ticket(ticket)
        assert result is None


class TestTicketRevocation:
    """Tests for ticket revocation."""

    @pytest.mark.asyncio
    async def test_revoke_existing_ticket(self, ticket_auth):
        """Existing ticket can be revoked."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        revoked = await ticket_auth.revoke_ticket(ticket)
        assert revoked is True

        # Ticket should no longer be valid
        result = await ticket_auth.validate_ticket(ticket)
        assert result is None

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_ticket(self, ticket_auth):
        """Revoking nonexistent ticket returns False."""
        revoked = await ticket_auth.revoke_ticket("nonexistent-ticket")
        assert revoked is False


class TestWebSocketTicketDataclass:
    """Tests for WebSocketTicket dataclass."""

    def test_to_json(self):
        """Ticket serializes to JSON correctly."""
        ticket = WebSocketTicket(
            ticket="test123",
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
            conversation_id="conv123",
            created_at=1000.0,
        )
        json_str = ticket.to_json()
        data = json.loads(json_str)

        assert data["ticket"] == "test123"
        assert data["user_id"] == "user123"
        assert data["tenant_id"] == "tenant456"
        assert data["session_id"] == "session789"
        assert data["conversation_id"] == "conv123"
        assert data["created_at"] == 1000.0

    def test_from_json(self):
        """Ticket deserializes from JSON correctly."""
        json_str = json.dumps({
            "ticket": "test123",
            "user_id": "user123",
            "tenant_id": "tenant456",
            "session_id": "session789",
            "conversation_id": "conv123",
            "created_at": 1000.0,
        })
        ticket = WebSocketTicket.from_json(json_str)

        assert ticket.ticket == "test123"
        assert ticket.user_id == "user123"
        assert ticket.tenant_id == "tenant456"
        assert ticket.session_id == "session789"
        assert ticket.conversation_id == "conv123"
        assert ticket.created_at == 1000.0

    def test_is_expired_fresh_ticket(self):
        """Fresh ticket is not expired."""
        ticket = WebSocketTicket(
            ticket="test123",
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        assert not ticket.is_expired()

    def test_is_expired_old_ticket(self):
        """Old ticket is expired."""
        ticket = WebSocketTicket(
            ticket="test123",
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
            created_at=time.time() - 200,  # 200 seconds ago
        )
        assert ticket.is_expired(max_age_seconds=120)

    def test_auto_created_at(self):
        """created_at is auto-set if not provided."""
        before = time.time()
        ticket = WebSocketTicket(
            ticket="test123",
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        after = time.time()

        assert before <= ticket.created_at <= after


class TestSecurityEdgeCases:
    """Security-focused edge case tests."""

    @pytest.mark.asyncio
    async def test_malformed_json_in_redis(self, ticket_auth, redis):
        """Malformed JSON in Redis returns None."""
        # Manually store invalid JSON
        redis.store["ws_ticket:fake123"] = "not valid json"
        result = await ticket_auth.validate_ticket("fake123")
        assert result is None

    @pytest.mark.asyncio
    async def test_ticket_mismatch_in_data(self, ticket_auth, redis):
        """Ticket string mismatch in stored data returns None."""
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )
        # Modify stored ticket to not match
        key = f"ws_ticket:{ticket}"
        data = json.loads(redis.store[key])
        data["ticket"] = "different-ticket"
        redis.store[key] = json.dumps(data)

        result = await ticket_auth.validate_ticket(ticket)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_fields_in_stored_data(self, ticket_auth, redis):
        """Missing required fields returns None."""
        # Manually store incomplete data
        redis.store["ws_ticket:fake123"] = json.dumps({
            "ticket": "fake123",
            # Missing user_id, tenant_id, session_id
        })
        result = await ticket_auth.validate_ticket("fake123")
        assert result is None
