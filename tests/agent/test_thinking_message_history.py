"""
Tests for message history handling with extended thinking enabled.

Verifies that conversation history is correctly passed to the API
when extended thinking is enabled, and that all message types
(USER, ASSISTANT, TOOL) are properly formatted.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.glp.agent.domain.entities import (
    Message,
    MessageRole,
    ToolCall,
)
from src.glp.agent.providers.anthropic import AnthropicProvider
from src.glp.agent.providers.base import LLMProviderConfig


@pytest.fixture
def config_with_thinking():
    """Create a config with thinking enabled."""
    return LLMProviderConfig(
        api_key="test-key",
        model="claude-sonnet-4-20250514",  # Model that supports thinking
        enable_thinking=True,
        thinking_budget=10000,
    )


@pytest.fixture
def config_without_thinking():
    """Create a config without thinking."""
    return LLMProviderConfig(
        api_key="test-key",
        model="claude-sonnet-4-20250514",
        enable_thinking=False,
    )


class TestMessageFormatting:
    """Tests for _format_messages_for_api with different message types."""

    def test_format_user_message(self, config_with_thinking):
        """USER messages are formatted correctly."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(config_with_thinking)

            messages = [
                Message(
                    role=MessageRole.USER,
                    content="What devices are in the inventory?",
                    conversation_id=uuid4(),
                )
            ]

            system, api_messages = provider._format_messages_for_api(messages)

            assert len(api_messages) == 1
            assert api_messages[0]["role"] == "user"
            assert api_messages[0]["content"] == "What devices are in the inventory?"

    def test_format_assistant_message(self, config_with_thinking):
        """ASSISTANT messages are formatted correctly."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(config_with_thinking)

            messages = [
                Message(
                    role=MessageRole.ASSISTANT,
                    content="I'll query the database for you.",
                    conversation_id=uuid4(),
                )
            ]

            system, api_messages = provider._format_messages_for_api(messages)

            assert len(api_messages) == 1
            assert api_messages[0]["role"] == "assistant"
            assert api_messages[0]["content"] == "I'll query the database for you."

    def test_format_assistant_with_tool_calls(self, config_with_thinking):
        """ASSISTANT messages with tool calls are formatted correctly."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(config_with_thinking)

            messages = [
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Let me run that query.",
                    tool_calls=[
                        ToolCall(
                            id="tool_123",
                            name="run_query",
                            arguments={"query": "SELECT * FROM devices"},
                        )
                    ],
                    conversation_id=uuid4(),
                )
            ]

            system, api_messages = provider._format_messages_for_api(messages)

            assert len(api_messages) == 1
            assert api_messages[0]["role"] == "assistant"
            assert isinstance(api_messages[0]["content"], list)

            # Should have text block and tool_use block
            content_blocks = api_messages[0]["content"]
            assert len(content_blocks) == 2

            text_block = content_blocks[0]
            assert text_block["type"] == "text"
            assert text_block["text"] == "Let me run that query."

            tool_block = content_blocks[1]
            assert tool_block["type"] == "tool_use"
            assert tool_block["id"] == "tool_123"
            assert tool_block["name"] == "run_query"
            assert tool_block["input"] == {"query": "SELECT * FROM devices"}

    def test_format_tool_result_message(self, config_with_thinking):
        """TOOL result messages are formatted correctly."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(config_with_thinking)

            messages = [
                Message(
                    role=MessageRole.TOOL,
                    content="Found 10 devices",
                    tool_calls=[
                        ToolCall(
                            id="tool_123",
                            name="run_query",
                            arguments={},
                        )
                    ],
                    conversation_id=uuid4(),
                )
            ]

            system, api_messages = provider._format_messages_for_api(messages)

            assert len(api_messages) == 1
            assert api_messages[0]["role"] == "user"
            assert isinstance(api_messages[0]["content"], list)

            content_blocks = api_messages[0]["content"]
            assert len(content_blocks) == 1
            assert content_blocks[0]["type"] == "tool_result"
            assert content_blocks[0]["tool_use_id"] == "tool_123"
            assert content_blocks[0]["content"] == "Found 10 devices"

    def test_format_system_message(self, config_with_thinking):
        """SYSTEM messages are prepended to system prompt."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(config_with_thinking)

            messages = [
                Message(
                    role=MessageRole.SYSTEM,
                    content="You are a helpful assistant.",
                    conversation_id=uuid4(),
                )
            ]

            system, api_messages = provider._format_messages_for_api(
                messages,
                system_prompt="Additional instructions."
            )

            # SYSTEM messages should not be in api_messages
            assert len(api_messages) == 0

            # Should be prepended to system prompt
            assert system == "You are a helpful assistant.\n\nAdditional instructions."

    def test_format_conversation_history(self, config_with_thinking):
        """Full conversation history is formatted correctly."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(config_with_thinking)

            conv_id = uuid4()
            messages = [
                Message(
                    role=MessageRole.USER,
                    content="Show me devices",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Let me query the database.",
                    tool_calls=[
                        ToolCall(
                            id="tool_1",
                            name="run_query",
                            arguments={"query": "SELECT * FROM devices LIMIT 10"},
                        )
                    ],
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.TOOL,
                    content="[10 devices returned]",
                    tool_calls=[
                        ToolCall(id="tool_1", name="run_query", arguments={})
                    ],
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Here are 10 devices from the inventory.",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.USER,
                    content="How many total devices?",
                    conversation_id=conv_id,
                ),
            ]

            system, api_messages = provider._format_messages_for_api(messages)

            # Should have all messages except SYSTEM
            assert len(api_messages) == 5

            # Check sequence
            assert api_messages[0]["role"] == "user"
            assert api_messages[0]["content"] == "Show me devices"

            assert api_messages[1]["role"] == "assistant"
            assert isinstance(api_messages[1]["content"], list)

            assert api_messages[2]["role"] == "user"
            assert isinstance(api_messages[2]["content"], list)
            assert api_messages[2]["content"][0]["type"] == "tool_result"

            assert api_messages[3]["role"] == "assistant"
            assert api_messages[3]["content"] == "Here are 10 devices from the inventory."

            assert api_messages[4]["role"] == "user"
            assert api_messages[4]["content"] == "How many total devices?"


class TestThinkingIntegration:
    """Tests that thinking parameter doesn't interfere with message history."""

    @pytest.mark.asyncio
    async def test_messages_passed_with_thinking_enabled(self, config_with_thinking):
        """Message history is passed correctly when thinking is enabled."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

            # Mock empty stream (just to verify call)
            async def empty_stream():
                return
                yield

            mock_stream.__aiter__ = lambda self: empty_stream()

            # Mock the messages.stream method
            mock_messages = MagicMock()
            mock_messages.stream = MagicMock(return_value=mock_stream)

            # Mock the client
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_client_class.return_value = mock_client

            provider = AnthropicProvider(config_with_thinking)

            conv_id = uuid4()
            messages = [
                Message(
                    role=MessageRole.USER,
                    content="What's in the inventory?",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Previous response",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.USER,
                    content="Show me more details",
                    conversation_id=conv_id,
                ),
            ]

            # Call chat
            events = []
            async for event in provider.chat(messages=messages):
                events.append(event)

            # Verify the API was called
            mock_messages.stream.assert_called_once()
            call_kwargs = mock_messages.stream.call_args[1]

            # Verify thinking parameters are set
            assert "thinking" in call_kwargs
            assert call_kwargs["thinking"]["type"] == "enabled"
            assert call_kwargs["thinking"]["budget_tokens"] == 10000

            # Verify messages are passed
            assert "messages" in call_kwargs
            api_messages = call_kwargs["messages"]
            assert len(api_messages) == 3

            # Verify message content
            assert api_messages[0]["role"] == "user"
            assert api_messages[0]["content"] == "What's in the inventory?"
            assert api_messages[1]["role"] == "assistant"
            assert api_messages[1]["content"] == "Previous response"
            assert api_messages[2]["role"] == "user"
            assert api_messages[2]["content"] == "Show me more details"

    @pytest.mark.asyncio
    async def test_messages_passed_without_thinking(self, config_without_thinking):
        """Message history is passed correctly when thinking is disabled."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

            # Mock empty stream
            async def empty_stream():
                return
                yield

            mock_stream.__aiter__ = lambda self: empty_stream()

            # Mock the messages.stream method
            mock_messages = MagicMock()
            mock_messages.stream = MagicMock(return_value=mock_stream)

            # Mock the client
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_client_class.return_value = mock_client

            provider = AnthropicProvider(config_without_thinking)

            conv_id = uuid4()
            messages = [
                Message(
                    role=MessageRole.USER,
                    content="Query 1",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Response 1",
                    conversation_id=conv_id,
                ),
            ]

            # Call chat
            events = []
            async for event in provider.chat(messages=messages):
                events.append(event)

            # Verify the API was called
            mock_messages.stream.assert_called_once()
            call_kwargs = mock_messages.stream.call_args[1]

            # Verify thinking is NOT set
            assert "thinking" not in call_kwargs

            # Verify messages are still passed correctly
            assert "messages" in call_kwargs
            api_messages = call_kwargs["messages"]
            assert len(api_messages) == 2

    @pytest.mark.asyncio
    async def test_tool_calls_in_history_with_thinking(self, config_with_thinking):
        """Tool calls in message history are preserved with thinking enabled."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

            # Mock empty stream
            async def empty_stream():
                return
                yield

            mock_stream.__aiter__ = lambda self: empty_stream()

            # Mock the messages.stream method
            mock_messages = MagicMock()
            mock_messages.stream = MagicMock(return_value=mock_stream)

            # Mock the client
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_client_class.return_value = mock_client

            provider = AnthropicProvider(config_with_thinking)

            conv_id = uuid4()
            messages = [
                Message(
                    role=MessageRole.USER,
                    content="Count devices",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Let me check.",
                    tool_calls=[
                        ToolCall(
                            id="tc_1",
                            name="run_query",
                            arguments={"query": "SELECT COUNT(*) FROM devices"},
                        )
                    ],
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.TOOL,
                    content="42",
                    tool_calls=[ToolCall(id="tc_1", name="run_query", arguments={})],
                    conversation_id=conv_id,
                ),
            ]

            # Call chat
            events = []
            async for event in provider.chat(messages=messages):
                events.append(event)

            # Verify the API was called
            call_kwargs = mock_messages.stream.call_args[1]

            # Verify thinking is enabled
            assert "thinking" in call_kwargs

            # Verify tool call history is preserved
            api_messages = call_kwargs["messages"]
            assert len(api_messages) == 3

            # Check tool_use block
            assert api_messages[1]["role"] == "assistant"
            content_blocks = api_messages[1]["content"]
            assert any(block["type"] == "tool_use" for block in content_blocks)
            tool_block = next(b for b in content_blocks if b["type"] == "tool_use")
            assert tool_block["id"] == "tc_1"
            assert tool_block["name"] == "run_query"

            # Check tool_result block
            assert api_messages[2]["role"] == "user"
            content_blocks = api_messages[2]["content"]
            assert content_blocks[0]["type"] == "tool_result"
            assert content_blocks[0]["tool_use_id"] == "tc_1"
            assert content_blocks[0]["content"] == "42"
