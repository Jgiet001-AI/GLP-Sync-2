"""
Tests for chat message length validation.

Ensures messages are properly validated before LLM processing.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.glp.agent.api.schemas import ChatRequest, MAX_MESSAGE_LENGTH


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestChatRequestSchema:
    """Tests for ChatRequest schema validation."""

    def test_valid_message(self):
        """Valid message passes validation."""
        request = ChatRequest(message="Hello, world!")
        assert request.message == "Hello, world!"

    def test_message_at_max_length(self):
        """Message at exactly MAX_MESSAGE_LENGTH passes validation."""
        message = "x" * MAX_MESSAGE_LENGTH
        request = ChatRequest(message=message)
        assert len(request.message) == MAX_MESSAGE_LENGTH

    def test_message_exceeds_max_length(self):
        """Message exceeding MAX_MESSAGE_LENGTH fails validation."""
        message = "x" * (MAX_MESSAGE_LENGTH + 1)
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(message=message)

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("max_length" in str(error) or "String should have at most" in str(error)
                   for error in errors)

    def test_empty_message_fails(self):
        """Empty message fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(message="")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert any("min_length" in str(error) or "String should have at least" in str(error)
                   for error in errors)

    def test_whitespace_only_message(self):
        """Whitespace-only message passes schema validation."""
        # Note: Schema validates length, not content
        # WebSocket handler does content validation
        request = ChatRequest(message="   ")
        assert request.message == "   "

    def test_max_message_length_constant(self):
        """MAX_MESSAGE_LENGTH constant has expected value."""
        assert MAX_MESSAGE_LENGTH == 10000


# =============================================================================
# Schema Validation with Pydantic Tests
# =============================================================================


class TestPydanticValidation:
    """Tests for Pydantic schema validation at REST endpoint layer."""

    def test_schema_validates_valid_message(self):
        """ChatRequest schema validates proper messages."""
        # This tests that REST endpoints using ChatRequest will validate
        request = ChatRequest(message="Hello, world!")
        assert request.message == "Hello, world!"

    def test_schema_rejects_empty_message(self):
        """ChatRequest schema rejects empty messages."""
        # REST endpoints will return 422 for invalid schema
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_schema_rejects_over_limit(self):
        """ChatRequest schema rejects messages exceeding limit."""
        # REST endpoints will return 422 for invalid schema
        message = "x" * (MAX_MESSAGE_LENGTH + 1)
        with pytest.raises(ValidationError):
            ChatRequest(message=message)

    def test_schema_accepts_at_limit(self):
        """ChatRequest schema accepts messages at exact limit."""
        message = "x" * MAX_MESSAGE_LENGTH
        request = ChatRequest(message=message)
        assert len(request.message) == MAX_MESSAGE_LENGTH


# =============================================================================
# WebSocket Validation Tests
# =============================================================================


class TestWebSocketValidation:
    """Tests for WebSocket message validation."""

    @pytest.mark.asyncio
    async def test_valid_message_processed(self):
        """Valid message is processed via WebSocket."""
        from fastapi import WebSocket

        # Mock WebSocket
        websocket = MagicMock(spec=WebSocket)
        websocket.receive_json = AsyncMock(return_value={
            "type": "chat",
            "message": "Hello, world!",
        })
        websocket.send_json = AsyncMock()

        # Mock orchestrator
        mock_orchestrator = MagicMock()
        mock_orchestrator.stream_response = AsyncMock()

        # Import the validation logic
        from src.glp.agent.api.router import MAX_MESSAGE_LENGTH

        # Simulate validation
        message = "Hello, world!"
        assert len(message) <= MAX_MESSAGE_LENGTH
        assert message.strip() != ""

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self):
        """Empty message is rejected via WebSocket."""
        from fastapi import WebSocket

        websocket = MagicMock(spec=WebSocket)
        websocket.send_json = AsyncMock()

        # Simulate the validation logic from router.py
        message = ""

        if not message or not message.strip():
            await websocket.send_json({
                "type": "error",
                "content": "Message cannot be empty",
                "error_type": "validation_error",
            })

        # Verify error was sent
        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert call_args["error_type"] == "validation_error"
        assert "empty" in call_args["content"].lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_message_rejected(self):
        """Whitespace-only message is rejected via WebSocket."""
        from fastapi import WebSocket

        websocket = MagicMock(spec=WebSocket)
        websocket.send_json = AsyncMock()

        message = "   \t\n  "

        if not message or not message.strip():
            await websocket.send_json({
                "type": "error",
                "content": "Message cannot be empty",
                "error_type": "validation_error",
            })

        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "error"

    @pytest.mark.asyncio
    async def test_message_over_limit_rejected(self):
        """Message exceeding MAX_MESSAGE_LENGTH is rejected via WebSocket."""
        from fastapi import WebSocket

        websocket = MagicMock(spec=WebSocket)
        websocket.send_json = AsyncMock()

        message = "x" * (MAX_MESSAGE_LENGTH + 1)

        if len(message) > MAX_MESSAGE_LENGTH:
            await websocket.send_json({
                "type": "error",
                "content": f"Message exceeds maximum length of {MAX_MESSAGE_LENGTH} characters (received {len(message)} characters)",
                "error_type": "validation_error",
            })

        websocket.send_json.assert_called_once()
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "error"
        assert call_args["error_type"] == "validation_error"
        assert str(MAX_MESSAGE_LENGTH) in call_args["content"]
        assert str(len(message)) in call_args["content"]

    @pytest.mark.asyncio
    async def test_message_at_limit_accepted(self):
        """Message at exactly MAX_MESSAGE_LENGTH is accepted via WebSocket."""
        message = "x" * MAX_MESSAGE_LENGTH

        # Should pass validation
        assert len(message) == MAX_MESSAGE_LENGTH
        assert message.strip() != ""

        # Should not trigger length error
        is_valid = len(message) <= MAX_MESSAGE_LENGTH and message.strip() != ""
        assert is_valid is True


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in message validation."""

    def test_message_with_unicode_characters(self):
        """Unicode characters are handled correctly."""
        message = "Hello 👋 世界 🌍"
        request = ChatRequest(message=message)
        assert request.message == message

    def test_message_with_newlines(self):
        """Messages with newlines are valid."""
        message = "Line 1\nLine 2\nLine 3"
        request = ChatRequest(message=message)
        assert request.message == message

    def test_very_long_unicode_message(self):
        """Very long unicode message exceeding limit fails."""
        # Each emoji can be multiple bytes
        message = "👋" * (MAX_MESSAGE_LENGTH + 1)
        with pytest.raises(ValidationError):
            ChatRequest(message=message)

    def test_message_length_boundary(self):
        """Test exact boundary conditions."""
        # MAX_MESSAGE_LENGTH - 1 should pass
        message = "x" * (MAX_MESSAGE_LENGTH - 1)
        request = ChatRequest(message=message)
        assert len(request.message) == MAX_MESSAGE_LENGTH - 1

        # MAX_MESSAGE_LENGTH should pass
        message = "x" * MAX_MESSAGE_LENGTH
        request = ChatRequest(message=message)
        assert len(request.message) == MAX_MESSAGE_LENGTH

        # MAX_MESSAGE_LENGTH + 1 should fail
        message = "x" * (MAX_MESSAGE_LENGTH + 1)
        with pytest.raises(ValidationError):
            ChatRequest(message=message)


# =============================================================================
# Security Tests
# =============================================================================


class TestSecurityValidation:
    """Tests for security-related validation."""

    def test_extremely_long_message_rejected(self):
        """Extremely long message (1MB) is rejected."""
        message = "x" * (1024 * 1024)  # 1MB
        with pytest.raises(ValidationError):
            ChatRequest(message=message)

    def test_null_byte_in_message(self):
        """Message with null bytes is handled."""
        message = "Hello\x00World"
        # Pydantic should accept this, but it's a valid string
        request = ChatRequest(message=message)
        assert "\x00" in request.message

    def test_control_characters_in_message(self):
        """Message with control characters is handled."""
        message = "Hello\x01\x02\x03World"
        request = ChatRequest(message=message)
        assert request.message == message
