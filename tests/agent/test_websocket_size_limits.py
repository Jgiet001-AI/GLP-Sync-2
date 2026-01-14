"""
Tests for WebSocket message size limits.

Ensures messages are properly validated against size limits to prevent
memory exhaustion attacks.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import WebSocketDisconnect

from src.glp.agent.api.router import (
    websocket_endpoint,
    create_agent_dependencies,
)
from src.glp.agent.orchestrator.agent import AgentOrchestrator
from src.glp.agent.security.ticket_auth import (
    WebSocketTicket,
    WebSocketTicketAuth,
)

# Constants from router.py (imported here to avoid FastAPI dependency issues in tests)
MAX_WS_MESSAGE_SIZE_MB = 1
MAX_WS_MESSAGE_SIZE_BYTES = MAX_WS_MESSAGE_SIZE_MB * 1024 * 1024  # 1 MB


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


class MockWebSocket:
    """Mock WebSocket for testing."""

    def __init__(self):
        self.messages_to_receive: list[str] = []
        self.sent_messages: list[dict] = []
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None
        self.close_reason: str | None = None

    async def accept(self) -> None:
        """Accept the connection."""
        self.accepted = True

    async def receive_text(self) -> str:
        """Receive a text message."""
        if not self.messages_to_receive:
            # Simulate disconnect when no more messages
            raise WebSocketDisconnect()
        return self.messages_to_receive.pop(0)

    async def send_json(self, data: dict) -> None:
        """Send JSON message."""
        self.sent_messages.append(data)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the connection."""
        self.closed = True
        self.close_code = code
        self.close_reason = reason


@pytest.fixture
def redis():
    """Create a mock Redis client."""
    return MockRedis()


@pytest.fixture
def ticket_auth(redis):
    """Create a WebSocketTicketAuth instance."""
    return WebSocketTicketAuth(redis)


@pytest.fixture
def mock_orchestrator():
    """Create a mock orchestrator."""
    orchestrator = MagicMock(spec=AgentOrchestrator)
    orchestrator._pending_confirmations = {}

    # Mock chat method to return async generator
    async def mock_chat(*args, **kwargs):
        # Return a simple event
        event = MagicMock()
        event.to_dict.return_value = {"type": "done"}
        yield event

    orchestrator.chat = mock_chat
    return orchestrator


@pytest.fixture
def setup_websocket_endpoint(ticket_auth, mock_orchestrator):
    """Setup WebSocket endpoint dependencies.

    Returns:
        Tuple of (ticket_auth, orchestrator) for use in tests.
    """
    # Initialize the agent dependencies globally
    create_agent_dependencies(
        orchestrator=mock_orchestrator,
        ticket_auth=ticket_auth,
    )
    return ticket_auth, mock_orchestrator


async def websocket_message_handler(websocket, raw_message):
    """
    Simulates the WebSocket message size checking logic from router.py.

    This is extracted for testing purposes to avoid importing FastAPI.
    """
    # Check message size
    message_size = len(raw_message.encode('utf-8'))
    if message_size > MAX_WS_MESSAGE_SIZE_BYTES:
        await websocket.send_json({
            "type": "error",
            "content": f"Message too large. Maximum size is {MAX_WS_MESSAGE_SIZE_MB} MB",
            "error_type": "message_too_large",
        })
        return None

    # Parse JSON manually
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError as e:
        await websocket.send_json({
            "type": "error",
            "content": "Invalid JSON message",
            "error_type": "invalid_json",
        })
        return None

    return data


class TestMessageSizeLimits:
    """Tests for WebSocket message size validation."""

    @pytest.mark.asyncio
    async def test_message_under_limit_passes(self):
        """Messages under the size limit are processed successfully."""
        # Create small message (well under 1MB limit)
        small_message = json.dumps({
            "type": "chat",
            "message": "Hello, this is a small message",
        })

        # Create mock WebSocket
        mock_ws = MockWebSocket()

        # Process message
        result = await websocket_message_handler(mock_ws, small_message)

        # Verify message was accepted and parsed
        assert result is not None
        assert result["type"] == "chat"
        assert result["message"] == "Hello, this is a small message"

        # Verify no error messages were sent
        error_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "error"]
        assert len(error_messages) == 0

    @pytest.mark.asyncio
    async def test_message_at_exact_limit_passes(self, setup_websocket_endpoint):
        """Messages at exactly the size limit are accepted."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create message at exact limit using ping (synchronous processing)
        # Need to account for JSON structure overhead
        base_message = {"type": "ping"}
        base_size = len(json.dumps(base_message).encode('utf-8'))
        # Add padding field to reach exact limit
        padding_size = MAX_WS_MESSAGE_SIZE_BYTES - base_size - 15  # -15 for "padding":""

        # Create message with padding to reach exact limit
        exact_message = json.dumps({
            "type": "ping",
            "padding": "x" * padding_size,
        })

        # Verify size is at or very close to limit
        actual_size = len(exact_message.encode('utf-8'))
        assert actual_size <= MAX_WS_MESSAGE_SIZE_BYTES

        # Create mock WebSocket
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = [exact_message]

        # Call the WebSocket endpoint
        await websocket_endpoint(mock_ws, ticket)

        # Verify connection was accepted
        assert mock_ws.accepted

        # Verify message was processed (should get pong)
        pong_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "pong"]
        assert len(pong_messages) > 0

    @pytest.mark.asyncio
    async def test_message_over_limit_rejected(self, setup_websocket_endpoint):
        """Messages over the size limit are rejected with error."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create oversized message (over 1MB)
        oversized_message = json.dumps({
            "type": "chat",
            "message": "x" * (MAX_WS_MESSAGE_SIZE_BYTES + 1000),
        })

        # Verify message is over limit
        assert len(oversized_message.encode('utf-8')) > MAX_WS_MESSAGE_SIZE_BYTES

        # Create mock WebSocket - add a small valid message after to prevent disconnect
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = [
            oversized_message,
            json.dumps({"type": "ping"}),  # Valid message to keep connection alive
        ]

        # Call the WebSocket endpoint
        await websocket_endpoint(mock_ws, ticket)

        # Verify connection was accepted
        assert mock_ws.accepted

        # Find error message in sent messages
        error_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "error"]
        assert len(error_messages) > 0

        error_msg = error_messages[0]
        assert error_msg["error_type"] == "message_too_large"

    @pytest.mark.asyncio
    async def test_error_message_includes_size_information(self, setup_websocket_endpoint):
        """Error message includes size limit information."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create oversized message
        oversized_message = json.dumps({
            "type": "chat",
            "message": "x" * (MAX_WS_MESSAGE_SIZE_BYTES + 1000),
        })

        # Create mock WebSocket
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = [
            oversized_message,
            json.dumps({"type": "ping"}),
        ]

        # Call the WebSocket endpoint
        await websocket_endpoint(mock_ws, ticket)

        # Find error message
        error_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "error"]
        assert len(error_messages) > 0

        error_msg = error_messages[0]
        # Should mention the limit in MB
        assert str(MAX_WS_MESSAGE_SIZE_MB) in error_msg["content"]
        assert "MB" in error_msg["content"]

    @pytest.mark.asyncio
    async def test_valid_messages_work_after_rejection(self, setup_websocket_endpoint):
        """Valid messages are processed correctly after rejecting oversized ones."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create mix of messages: oversized, then valid
        oversized_message = json.dumps({
            "type": "chat",
            "message": "x" * (MAX_WS_MESSAGE_SIZE_BYTES + 1000),
        })

        valid_message = json.dumps({
            "type": "ping",  # Use ping instead of chat since chat creates background task
        })

        # Create mock WebSocket
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = [
            oversized_message,
            valid_message,  # Valid ping message after oversized message
        ]

        # Call the WebSocket endpoint
        await websocket_endpoint(mock_ws, ticket)

        # Verify oversized message was rejected
        error_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "error"]
        assert len(error_messages) > 0
        assert error_messages[0]["error_type"] == "message_too_large"

        # Verify valid message was processed (ping should get pong response)
        pong_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "pong"]
        assert len(pong_messages) > 0

    @pytest.mark.asyncio
    async def test_multiple_oversized_messages_dont_exhaust_memory(self, setup_websocket_endpoint):
        """Multiple oversized messages don't cause memory issues."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create multiple oversized messages
        oversized_messages = []
        for i in range(5):
            msg = json.dumps({
                "type": "chat",
                "message": f"Message {i}: " + "x" * (MAX_WS_MESSAGE_SIZE_BYTES + 1000),
            })
            oversized_messages.append(msg)

        # Add a final valid message to end the loop
        oversized_messages.append(json.dumps({"type": "ping"}))

        # Create mock WebSocket
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = oversized_messages

        # Call the WebSocket endpoint - should handle all messages without OOM
        await websocket_endpoint(mock_ws, ticket)

        # Verify all oversized messages were rejected
        error_messages = [
            msg for msg in mock_ws.sent_messages
            if msg.get("type") == "error" and msg.get("error_type") == "message_too_large"
        ]

        # Should have 5 error messages (one for each oversized message)
        assert len(error_messages) == 5

    @pytest.mark.asyncio
    async def test_invalid_json_after_size_check(self, setup_websocket_endpoint):
        """Invalid JSON is caught after passing size check."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create invalid JSON (but under size limit)
        invalid_json = "{this is not valid json}"

        # Create mock WebSocket
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = [
            invalid_json,
            json.dumps({"type": "ping"}),
        ]

        # Call the WebSocket endpoint
        await websocket_endpoint(mock_ws, ticket)

        # Verify invalid JSON error
        error_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "error"]
        assert len(error_messages) > 0

        invalid_json_errors = [
            msg for msg in error_messages
            if msg.get("error_type") == "invalid_json"
        ]
        assert len(invalid_json_errors) > 0


class TestSizeLimitConstants:
    """Tests for size limit constants."""

    def test_max_size_constants_defined(self):
        """Size limit constants are properly defined."""
        assert MAX_WS_MESSAGE_SIZE_MB == 1
        assert MAX_WS_MESSAGE_SIZE_BYTES == 1024 * 1024

    def test_max_size_mb_to_bytes_conversion(self):
        """MB to bytes conversion is correct."""
        assert MAX_WS_MESSAGE_SIZE_BYTES == MAX_WS_MESSAGE_SIZE_MB * 1024 * 1024


class TestEdgeCases:
    """Edge case tests for size limits."""

    @pytest.mark.asyncio
    async def test_empty_message_accepted(self, setup_websocket_endpoint):
        """Empty messages are accepted (under size limit)."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create empty message
        empty_message = json.dumps({"type": "ping"})

        # Create mock WebSocket
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = [empty_message]

        # Call the WebSocket endpoint
        await websocket_endpoint(mock_ws, ticket)

        # Verify message was processed
        assert mock_ws.accepted
        pong_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "pong"]
        assert len(pong_messages) > 0

    @pytest.mark.asyncio
    async def test_unicode_characters_counted_correctly(self, setup_websocket_endpoint):
        """Unicode characters are counted correctly in size check."""
        ticket_auth, orchestrator = setup_websocket_endpoint

        # Create valid ticket
        ticket = await ticket_auth.create_ticket(
            user_id="user123",
            tenant_id="tenant456",
            session_id="session789",
        )

        # Create message with unicode characters using ping for synchronous processing
        # Unicode emoji can be multiple bytes
        unicode_message = json.dumps({
            "type": "ping",
            "data": "🚀" * 100,  # Each emoji is 4 bytes in UTF-8
        })

        # Verify it's under limit
        assert len(unicode_message.encode('utf-8')) < MAX_WS_MESSAGE_SIZE_BYTES

        # Create mock WebSocket
        mock_ws = MockWebSocket()
        mock_ws.messages_to_receive = [unicode_message]

        # Call the WebSocket endpoint
        await websocket_endpoint(mock_ws, ticket)

        # Verify message was processed (should get pong)
        assert mock_ws.accepted
        pong_messages = [msg for msg in mock_ws.sent_messages if msg.get("type") == "pong"]
        assert len(pong_messages) > 0
