"""
Tests for Extended Thinking Support with Message History.

Verifies that extended thinking works correctly with full conversation history,
including:
- Thinking configuration and enabling
- Thinking deltas are properly emitted and redacted
- Thinking budget is respected
- Temperature is set to 1 when thinking enabled
- Message history integration with thinking
- CoT redaction before storage
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.glp.agent.domain.entities import (
    ChatEventType,
    Message,
    MessageRole,
    ToolCall,
)
from src.glp.agent.orchestrator.agent import AgentConfig
from src.glp.agent.providers.anthropic import AnthropicProvider
from src.glp.agent.providers.base import LLMProviderConfig


# ============================================
# Fixtures
# ============================================


@pytest.fixture
def thinking_config():
    """Create a provider config with extended thinking enabled."""
    return LLMProviderConfig(
        api_key="test-key",
        model="claude-sonnet-4-20250514",  # Supports thinking
        enable_thinking=True,
        thinking_budget=8000,
        temperature=0.7,  # Will be overridden to 1 when thinking enabled
        max_tokens=4096,
    )


@pytest.fixture
def no_thinking_config():
    """Create a provider config without thinking."""
    return LLMProviderConfig(
        api_key="test-key",
        model="claude-sonnet-4-20250514",
        enable_thinking=False,
        temperature=0.7,
        max_tokens=4096,
    )


@pytest.fixture
def agent_config_with_thinking():
    """Create an agent config with thinking enabled."""
    return AgentConfig(
        enable_thinking=True,
        thinking_budget=10000,
        temperature=0.7,
        max_tokens=8192,
    )


@pytest.fixture
def agent_config_no_thinking():
    """Create an agent config without thinking."""
    return AgentConfig(
        enable_thinking=False,
        thinking_budget=None,
        temperature=0.7,
        max_tokens=4096,
    )


@pytest.fixture
def conversation_history():
    """Create a sample conversation history."""
    conv_id = uuid4()
    return [
        Message(
            role=MessageRole.USER,
            content="Show me all devices with expired subscriptions",
            conversation_id=conv_id,
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content="I'll query the database for devices with expired subscriptions.",
            tool_calls=[
                ToolCall(
                    id="tool_1",
                    name="run_query",
                    arguments={
                        "query": "SELECT d.* FROM devices d JOIN subscriptions s ON d.id = s.device_id WHERE s.end_time < NOW()"
                    },
                )
            ],
            conversation_id=conv_id,
        ),
        Message(
            role=MessageRole.TOOL,
            content="[5 devices returned with expired subscriptions]",
            tool_calls=[ToolCall(id="tool_1", name="run_query", arguments={})],
            conversation_id=conv_id,
        ),
        Message(
            role=MessageRole.ASSISTANT,
            content="I found 5 devices with expired subscriptions. Here are the details...",
            conversation_id=conv_id,
        ),
        Message(
            role=MessageRole.USER,
            content="Which of these should I prioritize for renewal based on usage?",
            conversation_id=conv_id,
        ),
    ]


# ============================================
# Configuration Tests
# ============================================


class TestThinkingConfiguration:
    """Tests for thinking configuration in provider and agent configs."""

    def test_provider_config_thinking_enabled(self, thinking_config):
        """Provider config has thinking enabled with correct budget."""
        assert thinking_config.enable_thinking is True
        assert thinking_config.thinking_budget == 8000

    def test_provider_config_thinking_disabled(self, no_thinking_config):
        """Provider config has thinking disabled by default."""
        assert no_thinking_config.enable_thinking is False

    def test_agent_config_thinking_enabled(self, agent_config_with_thinking):
        """Agent config has thinking enabled with correct budget."""
        assert agent_config_with_thinking.enable_thinking is True
        assert agent_config_with_thinking.thinking_budget == 10000

    def test_agent_config_thinking_disabled(self, agent_config_no_thinking):
        """Agent config has thinking disabled by default."""
        assert agent_config_no_thinking.enable_thinking is False
        assert agent_config_no_thinking.thinking_budget is None

    def test_provider_supports_thinking_model(self, thinking_config):
        """Provider detects models that support thinking."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(thinking_config)
            assert provider._supports_thinking is True

    def test_provider_unsupported_thinking_model(self):
        """Provider detects models that don't support thinking."""
        config = LLMProviderConfig(
            api_key="test-key",
            model="claude-3-haiku-20240307",  # Doesn't support thinking
            enable_thinking=True,
        )
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic"):
            provider = AnthropicProvider(config)
            assert provider._supports_thinking is False


# ============================================
# Thinking Parameters Tests
# ============================================


class TestThinkingParameters:
    """Tests for thinking parameters in API calls."""

    @pytest.mark.asyncio
    async def test_thinking_enabled_sets_parameters(self, thinking_config, conversation_history):
        """When thinking is enabled, correct parameters are set in API call."""
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

            provider = AnthropicProvider(thinking_config)

            # Call chat with conversation history
            events = []
            async for event in provider.chat(messages=conversation_history):
                events.append(event)

            # Verify API was called
            mock_messages.stream.assert_called_once()
            call_kwargs = mock_messages.stream.call_args[1]

            # Verify thinking parameter
            assert "thinking" in call_kwargs
            assert call_kwargs["thinking"]["type"] == "enabled"
            assert call_kwargs["thinking"]["budget_tokens"] == 8000

            # Verify temperature is forced to 1
            assert call_kwargs["temperature"] == 1

            # Verify max_tokens accounts for thinking budget
            assert call_kwargs["max_tokens"] >= 8000 + 4096

    @pytest.mark.asyncio
    async def test_thinking_disabled_no_parameters(self, no_thinking_config, conversation_history):
        """When thinking is disabled, thinking parameters are not set."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

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

            provider = AnthropicProvider(no_thinking_config)

            # Call chat
            events = []
            async for event in provider.chat(messages=conversation_history):
                events.append(event)

            # Verify API was called
            call_kwargs = mock_messages.stream.call_args[1]

            # Verify thinking is NOT set
            assert "thinking" not in call_kwargs

            # Verify temperature uses configured value
            assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_thinking_budget_customizable(self, conversation_history):
        """Thinking budget can be configured."""
        custom_budget_config = LLMProviderConfig(
            api_key="test-key",
            model="claude-sonnet-4-20250514",
            enable_thinking=True,
            thinking_budget=15000,
        )

        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

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

            provider = AnthropicProvider(custom_budget_config)

            # Call chat
            events = []
            async for event in provider.chat(messages=conversation_history):
                events.append(event)

            # Verify custom budget is used
            call_kwargs = mock_messages.stream.call_args[1]
            assert call_kwargs["thinking"]["budget_tokens"] == 15000


# ============================================
# Thinking Delta Events Tests
# ============================================


class TestThinkingDeltas:
    """Tests for thinking delta event handling and redaction."""

    @pytest.mark.asyncio
    async def test_thinking_deltas_emitted(self, thinking_config):
        """Thinking deltas are emitted as separate events."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock streaming response with thinking deltas
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

            # Create mock events
            class MockThinkingDelta:
                type = "thinking_delta"
                thinking = "First, I need to analyze the device usage patterns..."

            class MockContentBlockDelta:
                def __init__(self, delta):
                    self.type = "content_block_delta"
                    self.delta = delta

            class MockContentBlockStart:
                def __init__(self, block):
                    self.type = "content_block_start"
                    self.content_block = block

            class MockThinkingBlock:
                type = "thinking"

            # Mock event stream
            async def event_stream():
                # Thinking block start
                yield MockContentBlockStart(MockThinkingBlock())
                # Thinking deltas
                yield MockContentBlockDelta(MockThinkingDelta())
                # Done
                return

            mock_stream.__aiter__ = lambda self: event_stream()

            # Mock the messages.stream method
            mock_messages = MagicMock()
            mock_messages.stream = MagicMock(return_value=mock_stream)

            # Mock the client
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_client_class.return_value = mock_client

            provider = AnthropicProvider(thinking_config)

            messages = [
                Message(
                    role=MessageRole.USER,
                    content="Complex query requiring analysis",
                    conversation_id=uuid4(),
                )
            ]

            # Collect events
            events = []
            async for event in provider.chat(messages=messages):
                events.append(event)

            # Verify thinking delta event was emitted
            thinking_events = [e for e in events if e.type == ChatEventType.THINKING_DELTA]
            assert len(thinking_events) > 0
            assert thinking_events[0].content is not None

    @pytest.mark.asyncio
    async def test_thinking_deltas_redacted(self, thinking_config):
        """Sensitive data in thinking deltas is redacted."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock streaming response with sensitive thinking
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

            # Create mock events with sensitive data
            class MockThinkingDelta:
                type = "thinking_delta"
                thinking = "The password=secret123 should be checked against API key sk-1234567890"

            class MockContentBlockDelta:
                def __init__(self, delta):
                    self.type = "content_block_delta"
                    self.delta = delta

            class MockContentBlockStart:
                def __init__(self, block):
                    self.type = "content_block_start"
                    self.content_block = block

            class MockThinkingBlock:
                type = "thinking"

            # Mock event stream
            async def event_stream():
                yield MockContentBlockStart(MockThinkingBlock())
                yield MockContentBlockDelta(MockThinkingDelta())
                return

            mock_stream.__aiter__ = lambda self: event_stream()

            # Mock the messages.stream method
            mock_messages = MagicMock()
            mock_messages.stream = MagicMock(return_value=mock_stream)

            # Mock the client
            mock_client = MagicMock()
            mock_client.messages = mock_messages
            mock_client_class.return_value = mock_client

            provider = AnthropicProvider(thinking_config)

            messages = [
                Message(
                    role=MessageRole.USER,
                    content="Test query",
                    conversation_id=uuid4(),
                )
            ]

            # Collect events
            events = []
            async for event in provider.chat(messages=messages):
                events.append(event)

            # Verify thinking was redacted
            thinking_events = [e for e in events if e.type == ChatEventType.THINKING_DELTA]
            assert len(thinking_events) > 0

            # Check that sensitive data was redacted
            thinking_content = thinking_events[0].content
            assert "secret123" not in thinking_content
            assert "sk-1234567890" not in thinking_content
            assert "REDACTED" in thinking_content or "[REDACTED]" in thinking_content


# ============================================
# Message History Integration Tests
# ============================================


class TestMessageHistoryWithThinking:
    """Tests that message history works correctly with thinking enabled."""

    @pytest.mark.asyncio
    async def test_full_history_passed_with_thinking(self, thinking_config, conversation_history):
        """Full conversation history is passed when thinking is enabled."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

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

            provider = AnthropicProvider(thinking_config)

            # Call chat with full conversation history
            events = []
            async for event in provider.chat(messages=conversation_history):
                events.append(event)

            # Verify API was called with full history
            call_kwargs = mock_messages.stream.call_args[1]

            # Verify thinking is enabled
            assert "thinking" in call_kwargs

            # Verify all messages in history are present
            api_messages = call_kwargs["messages"]
            assert len(api_messages) == 5  # All messages from conversation_history

            # Verify message order and content
            assert api_messages[0]["role"] == "user"
            assert "expired subscriptions" in api_messages[0]["content"]

            assert api_messages[1]["role"] == "assistant"
            # Tool call should be formatted correctly
            assert isinstance(api_messages[1]["content"], list)

            assert api_messages[2]["role"] == "user"
            # Tool result should be formatted correctly
            assert isinstance(api_messages[2]["content"], list)
            assert api_messages[2]["content"][0]["type"] == "tool_result"

            assert api_messages[3]["role"] == "assistant"
            assert "5 devices" in api_messages[3]["content"]

            assert api_messages[4]["role"] == "user"
            assert "prioritize" in api_messages[4]["content"]

    @pytest.mark.asyncio
    async def test_tool_calls_preserved_with_thinking(self, thinking_config):
        """Tool calls in message history are preserved with thinking enabled."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

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

            provider = AnthropicProvider(thinking_config)

            # Create messages with tool calls
            conv_id = uuid4()
            messages = [
                Message(
                    role=MessageRole.USER,
                    content="Count all devices",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="I'll count the devices.",
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
                Message(
                    role=MessageRole.ASSISTANT,
                    content="There are 42 devices in total.",
                    conversation_id=conv_id,
                ),
                Message(
                    role=MessageRole.USER,
                    content="Now analyze their usage patterns",
                    conversation_id=conv_id,
                ),
            ]

            # Call chat
            events = []
            async for event in provider.chat(messages=messages):
                events.append(event)

            # Verify tool calls are preserved
            call_kwargs = mock_messages.stream.call_args[1]
            api_messages = call_kwargs["messages"]

            # Find the assistant message with tool call
            assistant_msg = api_messages[1]
            assert assistant_msg["role"] == "assistant"
            assert isinstance(assistant_msg["content"], list)

            # Verify tool_use block
            tool_use_block = next(
                (b for b in assistant_msg["content"] if b.get("type") == "tool_use"),
                None
            )
            assert tool_use_block is not None
            assert tool_use_block["id"] == "tc_1"
            assert tool_use_block["name"] == "run_query"
            assert tool_use_block["input"]["query"] == "SELECT COUNT(*) FROM devices"

            # Verify tool_result block
            tool_result_msg = api_messages[2]
            assert tool_result_msg["role"] == "user"
            tool_result_block = tool_result_msg["content"][0]
            assert tool_result_block["type"] == "tool_result"
            assert tool_result_block["tool_use_id"] == "tc_1"
            assert tool_result_block["content"] == "42"


# ============================================
# Edge Cases and Error Handling
# ============================================


class TestThinkingEdgeCases:
    """Tests for edge cases and error handling with thinking."""

    @pytest.mark.asyncio
    async def test_thinking_with_empty_history(self, thinking_config):
        """Thinking works with no prior conversation history."""
        with patch("src.glp.agent.providers.anthropic.AsyncAnthropic") as mock_client_class:
            # Mock the streaming response
            mock_stream = AsyncMock()
            mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
            mock_stream.__aexit__ = AsyncMock()

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

            provider = AnthropicProvider(thinking_config)

            # Single message, no history
            messages = [
                Message(
                    role=MessageRole.USER,
                    content="What's the weather?",
                    conversation_id=uuid4(),
                )
            ]

            # Call chat
            events = []
            async for event in provider.chat(messages=messages):
                events.append(event)

            # Verify thinking is still enabled
            call_kwargs = mock_messages.stream.call_args[1]
            assert "thinking" in call_kwargs
            assert call_kwargs["thinking"]["type"] == "enabled"

    def test_thinking_config_default_values(self):
        """Thinking config uses sensible defaults."""
        config = LLMProviderConfig(
            api_key="test-key",
            model="claude-sonnet-4-20250514",
        )

        # Default should be thinking disabled
        assert config.enable_thinking is False
        # Default budget should be set
        assert config.thinking_budget == 10000

    def test_thinking_config_override_budget(self):
        """Thinking budget can be overridden."""
        config = LLMProviderConfig(
            api_key="test-key",
            model="claude-sonnet-4-20250514",
            enable_thinking=True,
            thinking_budget=20000,
        )

        assert config.thinking_budget == 20000


# ============================================
# Integration with Agent Config
# ============================================


class TestAgentConfigIntegration:
    """Tests for agent config thinking integration."""

    def test_agent_config_passes_thinking_to_provider(self):
        """Agent config thinking settings are used by provider."""
        agent_config = AgentConfig(
            enable_thinking=True,
            thinking_budget=12000,
        )

        # Create provider config from agent config
        provider_config = LLMProviderConfig(
            api_key="test-key",
            model="claude-sonnet-4-20250514",
            enable_thinking=agent_config.enable_thinking,
            thinking_budget=agent_config.thinking_budget or 10000,
        )

        assert provider_config.enable_thinking is True
        assert provider_config.thinking_budget == 12000

    def test_agent_config_thinking_disabled_default(self):
        """Agent config has thinking disabled by default."""
        agent_config = AgentConfig()

        assert agent_config.enable_thinking is False
        assert agent_config.thinking_budget is None
