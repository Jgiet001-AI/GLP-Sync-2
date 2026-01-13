"""
Integration tests for OpenAI provider and embeddings.

Tests that OpenAI chat and embedding functionality work correctly.
"""

import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.glp.agent.providers.openai import OpenAIProvider, OPENAI_AVAILABLE
from src.glp.agent.providers.base import LLMProviderConfig
from src.glp.agent.domain.entities import Message, MessageRole, ChatEventType


# Skip if openai not installed
pytestmark = pytest.mark.skipif(
    not OPENAI_AVAILABLE,
    reason="openai package not installed"
)


@pytest.fixture
def openai_config():
    """Test OpenAI config."""
    return LLMProviderConfig(
        api_key="test-api-key",
        model="gpt-4o",
        embedding_model="text-embedding-3-large",
    )


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI async client."""
    client = MagicMock()

    # Mock embeddings
    mock_embedding_response = MagicMock()
    mock_embedding_response.data = [
        MagicMock(embedding=[0.1] * 3072)  # text-embedding-3-large dimension
    ]
    client.embeddings.create = AsyncMock(return_value=mock_embedding_response)

    # Mock chat completions with streaming
    async def mock_stream():
        # Yield text delta
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"
        chunk1.choices[0].delta.tool_calls = None
        chunk1.choices[0].finish_reason = None
        yield chunk1

        # Yield finish
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world!"
        chunk2.choices[0].delta.tool_calls = None
        chunk2.choices[0].finish_reason = "stop"
        yield chunk2

    client.chat.completions.create = AsyncMock(return_value=mock_stream())

    return client


class TestOpenAIProvider:
    """Tests for OpenAI provider."""

    def test_init_success(self, openai_config):
        """Provider initializes successfully."""
        with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
            provider = OpenAIProvider(openai_config)
            assert provider.config.model == "gpt-4o"
            assert provider.embedding_model == "text-embedding-3-large"

    def test_supports_tools(self, openai_config):
        """OpenAI supports tool calling."""
        with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
            provider = OpenAIProvider(openai_config)
            assert provider.supports_tools is True

    def test_default_embedding_model(self):
        """Default embedding model is text-embedding-3-large."""
        config = LLMProviderConfig(
            api_key="test-key",
            model="gpt-4o",
        )
        with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
            provider = OpenAIProvider(config)
            assert provider.embedding_model == "text-embedding-3-large"


class TestOpenAIEmbeddings:
    """Tests for OpenAI embedding functionality."""

    @pytest.mark.asyncio
    async def test_embed_single_text(self, openai_config, mock_openai_client):
        """Single text embedding works."""
        with patch("src.glp.agent.providers.openai.AsyncOpenAI", return_value=mock_openai_client):
            provider = OpenAIProvider(openai_config)
            provider.client = mock_openai_client

            embedding, model, dimension = await provider.embed("test text")

            assert len(embedding) == 3072
            assert model == "text-embedding-3-large"
            assert dimension == 3072
            mock_openai_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-large",
                input="test text",
            )

    @pytest.mark.asyncio
    async def test_embed_batch(self, openai_config, mock_openai_client):
        """Batch embedding works."""
        # Setup batch response
        mock_batch_response = MagicMock()
        mock_batch_response.data = [
            MagicMock(embedding=[0.1] * 3072),
            MagicMock(embedding=[0.2] * 3072),
        ]
        mock_openai_client.embeddings.create = AsyncMock(return_value=mock_batch_response)

        with patch("src.glp.agent.providers.openai.AsyncOpenAI", return_value=mock_openai_client):
            provider = OpenAIProvider(openai_config)
            provider.client = mock_openai_client

            results = await provider.embed_batch(["text1", "text2"])

            assert len(results) == 2
            assert all(len(r[0]) == 3072 for r in results)
            mock_openai_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-large",
                input=["text1", "text2"],
            )

    @pytest.mark.asyncio
    async def test_embed_empty_batch(self, openai_config, mock_openai_client):
        """Empty batch returns empty list."""
        with patch("src.glp.agent.providers.openai.AsyncOpenAI", return_value=mock_openai_client):
            provider = OpenAIProvider(openai_config)
            provider.client = mock_openai_client

            results = await provider.embed_batch([])

            assert results == []
            mock_openai_client.embeddings.create.assert_not_called()


class TestOpenAIChat:
    """Tests for OpenAI chat functionality."""

    @pytest.mark.asyncio
    async def test_chat_streaming(self, openai_config):
        """Chat streaming produces correct events."""
        mock_client = MagicMock()

        async def mock_stream():
            # Text delta
            chunk1 = MagicMock()
            chunk1.choices = [MagicMock()]
            chunk1.choices[0].delta.content = "Hello"
            chunk1.choices[0].delta.tool_calls = None
            chunk1.choices[0].finish_reason = None
            yield chunk1

            # More text
            chunk2 = MagicMock()
            chunk2.choices = [MagicMock()]
            chunk2.choices[0].delta.content = " world"
            chunk2.choices[0].delta.tool_calls = None
            chunk2.choices[0].finish_reason = "stop"
            yield chunk2

        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        with patch("src.glp.agent.providers.openai.AsyncOpenAI", return_value=mock_client):
            provider = OpenAIProvider(openai_config)
            provider.client = mock_client

            messages = [Message(role=MessageRole.USER, content="Hi")]

            events = []
            async for event in provider.chat(messages):
                events.append(event)

            # Should have text deltas and done
            text_events = [e for e in events if e.type == ChatEventType.TEXT_DELTA]
            done_events = [e for e in events if e.type == ChatEventType.DONE]

            assert len(text_events) >= 1
            assert len(done_events) == 1

    @pytest.mark.asyncio
    async def test_message_formatting_with_tool_calls(self, openai_config):
        """Messages with tool calls are formatted correctly for OpenAI."""
        from src.glp.agent.domain.entities import ToolCall

        with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
            provider = OpenAIProvider(openai_config)

            messages = [
                Message(role=MessageRole.USER, content="Search for devices"),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="I'll search for devices.",
                    tool_calls=[
                        ToolCall(id="call_123", name="search_devices", arguments={"query": "switch"})
                    ],
                ),
                Message(
                    role=MessageRole.TOOL,
                    content='[{"id": "1", "name": "switch1"}]',
                    tool_calls=[ToolCall(id="call_123", name="search_devices", arguments={})],
                ),
            ]

            formatted = provider._format_messages_for_api(messages, "System prompt")

            # Check system message
            assert formatted[0]["role"] == "system"
            assert formatted[0]["content"] == "System prompt"

            # Check user message
            assert formatted[1]["role"] == "user"

            # Check assistant with tool_calls
            assert formatted[2]["role"] == "assistant"
            assert "tool_calls" in formatted[2]
            assert formatted[2]["tool_calls"][0]["id"] == "call_123"

            # Check tool result
            assert formatted[3]["role"] == "tool"
            assert formatted[3]["tool_call_id"] == "call_123"


class TestEmbeddingDimensions:
    """Tests for embedding dimension handling."""

    def test_known_dimensions(self, openai_config):
        """Known embedding models have correct dimensions."""
        with patch("src.glp.agent.providers.openai.AsyncOpenAI"):
            provider = OpenAIProvider(openai_config)

            assert provider.EMBEDDING_DIMENSIONS["text-embedding-3-small"] == 1536
            assert provider.EMBEDDING_DIMENSIONS["text-embedding-3-large"] == 3072
            assert provider.EMBEDDING_DIMENSIONS["text-embedding-ada-002"] == 1536
