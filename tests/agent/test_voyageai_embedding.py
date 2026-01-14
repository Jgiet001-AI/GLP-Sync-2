"""
Integration tests for VoyageAI provider and embeddings.

Tests that VoyageAI embedding functionality works correctly.
Note: VoyageAI only supports embeddings, not chat.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.glp.agent.providers.voyageai import VoyageAIProvider, VOYAGEAI_AVAILABLE
from src.glp.agent.providers.base import LLMProviderConfig, LLMProviderError
from src.glp.agent.domain.entities import Message, MessageRole, ChatEventType, ErrorType


# Skip if voyageai not installed
pytestmark = pytest.mark.skipif(
    not VOYAGEAI_AVAILABLE,
    reason="voyageai package not installed"
)


@pytest.fixture
def voyageai_config():
    """Test VoyageAI config."""
    return LLMProviderConfig(
        api_key="pa-test-api-key",
        model="voyage-2",
        embedding_model="voyage-2",
    )


@pytest.fixture
def mock_voyageai_client():
    """Mock VoyageAI client."""
    client = MagicMock()

    # Mock embeddings response
    mock_embedding_response = MagicMock()
    mock_embedding_response.embeddings = [
        [0.1] * 1024  # voyage-2 dimension
    ]
    client.embed = MagicMock(return_value=mock_embedding_response)

    return client


class TestVoyageAIProvider:
    """Tests for VoyageAI provider."""

    def test_init_success(self, voyageai_config):
        """Provider initializes successfully."""
        with patch("src.glp.agent.providers.voyageai.voyageai.Client"):
            provider = VoyageAIProvider(voyageai_config)
            assert provider.config.model == "voyage-2"
            assert provider.embedding_model == "voyage-2"

    def test_init_without_package(self):
        """Provider raises ImportError if voyageai not installed."""
        config = LLMProviderConfig(
            api_key="test-key",
            model="voyage-2",
        )

        with patch("src.glp.agent.providers.voyageai.VOYAGEAI_AVAILABLE", False):
            with pytest.raises(ImportError, match="voyageai package is required"):
                VoyageAIProvider(config)

    def test_supports_tools(self, voyageai_config):
        """VoyageAI does not support tool calling."""
        with patch("src.glp.agent.providers.voyageai.voyageai.Client"):
            provider = VoyageAIProvider(voyageai_config)
            assert provider.supports_tools is False

    def test_supports_streaming(self, voyageai_config):
        """VoyageAI does not support streaming."""
        with patch("src.glp.agent.providers.voyageai.voyageai.Client"):
            provider = VoyageAIProvider(voyageai_config)
            assert provider.supports_streaming is False

    def test_default_embedding_model(self):
        """Default embedding model is voyage-2."""
        config = LLMProviderConfig(
            api_key="test-key",
            model="voyage-2",
        )
        with patch("src.glp.agent.providers.voyageai.voyageai.Client"):
            provider = VoyageAIProvider(config)
            assert provider.embedding_model == "voyage-2"


class TestVoyageAIEmbeddings:
    """Tests for VoyageAI embedding functionality."""

    @pytest.mark.asyncio
    async def test_embed_single_text(self, voyageai_config, mock_voyageai_client):
        """Single text embedding works."""
        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            embedding, model, dimension = await provider.embed("test text")

            assert len(embedding) == 1024
            assert model == "voyage-2"
            assert dimension == 1024
            mock_voyageai_client.embed.assert_called_once_with(
                texts=["test text"],
                model="voyage-2",
            )

    @pytest.mark.asyncio
    async def test_embed_batch(self, voyageai_config, mock_voyageai_client):
        """Batch embedding works."""
        # Setup batch response
        mock_batch_response = MagicMock()
        mock_batch_response.embeddings = [
            [0.1] * 1024,
            [0.2] * 1024,
        ]
        mock_voyageai_client.embed = MagicMock(return_value=mock_batch_response)

        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            results = await provider.embed_batch(["text1", "text2"])

            assert len(results) == 2
            assert all(len(r[0]) == 1024 for r in results)
            assert all(r[1] == "voyage-2" for r in results)
            assert all(r[2] == 1024 for r in results)
            mock_voyageai_client.embed.assert_called_once_with(
                texts=["text1", "text2"],
                model="voyage-2",
            )

    @pytest.mark.asyncio
    async def test_embed_empty_batch(self, voyageai_config, mock_voyageai_client):
        """Empty batch returns empty list."""
        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            results = await provider.embed_batch([])

            assert results == []
            mock_voyageai_client.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_embed_with_large_model(self, mock_voyageai_client):
        """Embedding with voyage-large-2 returns correct dimension."""
        config = LLMProviderConfig(
            api_key="test-key",
            model="voyage-2",
            embedding_model="voyage-large-2",
        )

        # Mock response for large model
        mock_response = MagicMock()
        mock_response.embeddings = [[0.1] * 1536]
        mock_voyageai_client.embed = MagicMock(return_value=mock_response)

        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(config)
            provider.client = mock_voyageai_client

            embedding, model, dimension = await provider.embed("test")

            assert len(embedding) == 1536
            assert model == "voyage-large-2"
            assert dimension == 1536


class TestVoyageAIChat:
    """Tests for VoyageAI chat functionality (should not be supported)."""

    @pytest.mark.asyncio
    async def test_chat_not_supported(self, voyageai_config):
        """Chat returns error event indicating it's not supported."""
        with patch("src.glp.agent.providers.voyageai.voyageai.Client"):
            provider = VoyageAIProvider(voyageai_config)

            messages = [Message(role=MessageRole.USER, content="Hi")]

            events = []
            async for event in provider.chat(messages):
                events.append(event)

            # Should have error and done events
            error_events = [e for e in events if e.type == ChatEventType.ERROR]
            done_events = [e for e in events if e.type == ChatEventType.DONE]

            assert len(error_events) == 1
            assert len(done_events) == 1
            assert "only supports embeddings" in error_events[0].content.lower()
            assert error_events[0].error_type == ErrorType.FATAL


class TestVoyageAIErrorHandling:
    """Tests for VoyageAI error handling."""

    @pytest.mark.asyncio
    async def test_embed_rate_limit_error(self, voyageai_config, mock_voyageai_client):
        """Rate limit errors are handled correctly."""
        mock_voyageai_client.embed = MagicMock(
            side_effect=Exception("Rate limit exceeded (429)")
        )

        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            with pytest.raises(LLMProviderError) as exc_info:
                await provider.embed("test")

            assert exc_info.value.error_type == ErrorType.RATE_LIMIT
            assert "rate limited" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_embed_timeout_error(self, voyageai_config, mock_voyageai_client):
        """Timeout errors are handled correctly."""
        mock_voyageai_client.embed = MagicMock(
            side_effect=Exception("Request timeout")
        )

        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            with pytest.raises(LLMProviderError) as exc_info:
                await provider.embed("test")

            assert exc_info.value.error_type == ErrorType.TIMEOUT
            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_embed_generic_error(self, voyageai_config, mock_voyageai_client):
        """Generic errors are handled correctly."""
        mock_voyageai_client.embed = MagicMock(
            side_effect=Exception("Something went wrong")
        )

        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            with pytest.raises(LLMProviderError) as exc_info:
                await provider.embed("test")

            assert exc_info.value.error_type == ErrorType.RECOVERABLE
            assert "embedding failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_embed_batch_rate_limit_error(self, voyageai_config, mock_voyageai_client):
        """Batch embedding rate limit errors are handled correctly."""
        mock_voyageai_client.embed = MagicMock(
            side_effect=Exception("Rate limit exceeded")
        )

        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            with pytest.raises(LLMProviderError) as exc_info:
                await provider.embed_batch(["text1", "text2"])

            assert exc_info.value.error_type == ErrorType.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_embed_batch_generic_error(self, voyageai_config, mock_voyageai_client):
        """Batch embedding generic errors are handled correctly."""
        mock_voyageai_client.embed = MagicMock(
            side_effect=Exception("API error")
        )

        with patch("src.glp.agent.providers.voyageai.voyageai.Client", return_value=mock_voyageai_client):
            provider = VoyageAIProvider(voyageai_config)
            provider.client = mock_voyageai_client

            with pytest.raises(LLMProviderError) as exc_info:
                await provider.embed_batch(["text1", "text2"])

            assert exc_info.value.error_type == ErrorType.RECOVERABLE
            assert "batch embedding failed" in str(exc_info.value).lower()


class TestEmbeddingDimensions:
    """Tests for embedding dimension handling."""

    def test_known_dimensions(self, voyageai_config):
        """Known embedding models have correct dimensions."""
        with patch("src.glp.agent.providers.voyageai.voyageai.Client"):
            provider = VoyageAIProvider(voyageai_config)

            assert provider.EMBEDDING_DIMENSIONS["voyage-2"] == 1024
            assert provider.EMBEDDING_DIMENSIONS["voyage-large-2"] == 1536
            assert provider.EMBEDDING_DIMENSIONS["voyage-code-2"] == 1536
            assert provider.EMBEDDING_DIMENSIONS["voyage-lite-02-instruct"] == 1024
