"""
Unit tests for Ollama provider.

Tests that Ollama chat and embedding functionality work correctly.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.glp.agent.providers.ollama import OllamaProvider, OLLAMA_AVAILABLE
from src.glp.agent.providers.base import LLMProviderConfig
from src.glp.agent.domain.entities import Message, MessageRole, ChatEventType, ToolCall


# Skip if httpx not installed
pytestmark = pytest.mark.skipif(
    not OLLAMA_AVAILABLE,
    reason="httpx package not installed"
)


@pytest.fixture
def ollama_config():
    """Test Ollama config."""
    return LLMProviderConfig(
        api_key="not-needed",  # Ollama doesn't require auth
        model="qwen3:4b",
        base_url="http://localhost:11434",
        embedding_model="nomic-embed-text",
    )


@pytest.fixture
def mock_httpx_client():
    """Mock httpx async client."""
    client = MagicMock()

    # Mock embeddings
    mock_embedding_response = MagicMock()
    mock_embedding_response.json.return_value = {
        "embedding": [0.1] * 768  # nomic-embed-text dimension
    }
    client.post = AsyncMock(return_value=mock_embedding_response)

    # Mock chat streaming
    class StreamContext:
        """Mock async context manager for streaming."""
        def __init__(self):
            self.stream_response = MagicMock()
            self.stream_response.raise_for_status = MagicMock()

            async def mock_aiter_lines():
                # Yield text chunk
                yield json.dumps({
                    "message": {"content": "Hello", "role": "assistant"},
                    "done": False
                })
                # Yield more text
                yield json.dumps({
                    "message": {"content": " world!", "role": "assistant"},
                    "done": False
                })
                # Yield done
                yield json.dumps({
                    "message": {"content": "", "role": "assistant"},
                    "done": True
                })

            self.stream_response.aiter_lines = mock_aiter_lines

        async def __aenter__(self):
            return self.stream_response

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    client.stream = MagicMock(return_value=StreamContext())
    client.aclose = AsyncMock()

    return client


class TestOllamaProvider:
    """Tests for Ollama provider initialization."""

    def test_init_success(self, ollama_config):
        """Provider initializes successfully."""
        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(ollama_config)
            assert provider.config.model == "qwen3:4b"
            assert provider.base_url == "http://localhost:11434"
            assert provider.embedding_model == "nomic-embed-text"

    def test_supports_tools(self, ollama_config):
        """Ollama supports tool calling (model-dependent)."""
        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(ollama_config)
            assert provider.supports_tools is True

    def test_default_values(self):
        """Default values are set correctly."""
        config = LLMProviderConfig(
            api_key="not-needed",
            model="llama3",
        )
        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(config)
            assert provider.base_url == OllamaProvider.DEFAULT_BASE_URL
            assert provider.embedding_model == OllamaProvider.DEFAULT_EMBEDDING_MODEL

    def test_init_without_httpx(self):
        """Provider raises ImportError if httpx not available."""
        with patch("src.glp.agent.providers.ollama.OLLAMA_AVAILABLE", False):
            config = LLMProviderConfig(api_key="test", model="qwen3:4b")
            with pytest.raises(ImportError, match="httpx package is required"):
                OllamaProvider(config)


class TestOllamaChat:
    """Tests for Ollama chat functionality."""

    @pytest.mark.asyncio
    async def test_chat_streaming(self, ollama_config, mock_httpx_client):
        """Chat streaming produces correct events."""
        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(ollama_config)
            provider.client = mock_httpx_client

            messages = [Message(role=MessageRole.USER, content="Hi")]

            events = []
            async for event in provider.chat(messages):
                events.append(event)

            # Should have text deltas and done
            text_events = [e for e in events if e.type == ChatEventType.TEXT_DELTA]
            done_events = [e for e in events if e.type == ChatEventType.DONE]

            assert len(text_events) >= 2  # "Hello" and " world!"
            assert len(done_events) == 1

            # Verify content
            full_text = "".join(e.content for e in text_events if e.content)
            assert full_text == "Hello world!"

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, ollama_config):
        """Chat with tools includes them in request."""
        from src.glp.agent.domain.entities import ToolDefinition

        # Setup mock to capture request
        request_payload = {}

        class CaptureStreamContext:
            def __init__(self, *args, **kwargs):
                request_payload.update(kwargs.get("json", {}))
                self.stream_response = MagicMock()
                self.stream_response.raise_for_status = MagicMock()

                async def mock_aiter_lines():
                    yield json.dumps({
                        "message": {"content": "Using tool", "role": "assistant"},
                        "done": True
                    })

                self.stream_response.aiter_lines = mock_aiter_lines

            async def __aenter__(self):
                return self.stream_response

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_client = MagicMock()
        mock_client.stream = MagicMock(side_effect=CaptureStreamContext)
        mock_client.aclose = AsyncMock()

        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(ollama_config)
            provider.client = mock_client

            messages = [Message(role=MessageRole.USER, content="Hi")]
            tools = [
                ToolDefinition(
                    name="test_tool",
                    description="A test tool",
                    parameters={
                        "type": "object",
                        "properties": {
                            "arg": {"type": "string"}
                        }
                    }
                )
            ]

            events = []
            async for event in provider.chat(messages, tools=tools):
                events.append(event)

            # Verify tools were included in request
            assert "tools" in request_payload
            assert len(request_payload["tools"]) == 1
            assert request_payload["tools"][0]["type"] == "function"

    @pytest.mark.asyncio
    async def test_message_formatting_with_tool_calls(self, ollama_config):
        """Messages with tool calls are formatted correctly."""
        request_payload = {}

        class CaptureStreamContext:
            def __init__(self, *args, **kwargs):
                request_payload.update(kwargs.get("json", {}))
                self.stream_response = MagicMock()
                self.stream_response.raise_for_status = MagicMock()

                async def mock_aiter_lines():
                    yield json.dumps({
                        "message": {"content": "OK", "role": "assistant"},
                        "done": True
                    })

                self.stream_response.aiter_lines = mock_aiter_lines

            async def __aenter__(self):
                return self.stream_response

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_client = MagicMock()
        mock_client.stream = MagicMock(side_effect=CaptureStreamContext)
        mock_client.aclose = AsyncMock()

        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(ollama_config)
            provider.client = mock_client

            messages = [
                Message(role=MessageRole.USER, content="Hi"),
                Message(
                    role=MessageRole.ASSISTANT,
                    content="Let me help",
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name="test_tool",
                            arguments={"arg": "value"}
                        )
                    ]
                ),
                Message(
                    role=MessageRole.TOOL,
                    content='{"result": "success"}'
                )
            ]

            events = []
            async for event in provider.chat(messages):
                events.append(event)

            # Verify message formatting in the captured payload
            formatted = request_payload["messages"]
            assert len(formatted) == 3

            # User message
            assert formatted[0]["role"] == "user"
            assert formatted[0]["content"] == "Hi"

            # Assistant with tool call
            assert formatted[1]["role"] == "assistant"
            assert "test_tool" in formatted[1]["content"]
            assert "arg" in formatted[1]["content"]

            # Tool result as user message
            assert formatted[2]["role"] == "user"
            assert "Tool result:" in formatted[2]["content"]

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self, ollama_config):
        """System prompt is added to messages."""
        request_payload = {}

        class CaptureStreamContext:
            def __init__(self, *args, **kwargs):
                request_payload.update(kwargs.get("json", {}))
                self.stream_response = MagicMock()
                self.stream_response.raise_for_status = MagicMock()

                async def mock_aiter_lines():
                    yield json.dumps({"message": {"content": "OK"}, "done": True})

                self.stream_response.aiter_lines = mock_aiter_lines

            async def __aenter__(self):
                return self.stream_response

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_client = MagicMock()
        mock_client.stream = MagicMock(side_effect=CaptureStreamContext)
        mock_client.aclose = AsyncMock()

        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(ollama_config)
            provider.client = mock_client

            messages = [Message(role=MessageRole.USER, content="Hi")]

            events = []
            async for event in provider.chat(messages, system_prompt="You are helpful"):
                events.append(event)

            # Verify system message is first
            assert request_payload["messages"][0]["role"] == "system"
            assert request_payload["messages"][0]["content"] == "You are helpful"


class TestOllamaEmbeddings:
    """Tests for Ollama embedding functionality."""

    @pytest.mark.asyncio
    async def test_embed_single_text(self, ollama_config, mock_httpx_client):
        """Single text embedding works."""
        with patch("src.glp.agent.providers.ollama.httpx"):
            provider = OllamaProvider(ollama_config)
            provider.client = mock_httpx_client

            embedding, model, dimension = await provider.embed("test text")

            assert len(embedding) == 768
            assert model == "nomic-embed-text"
            assert dimension == 768

            # Verify API call
            mock_httpx_client.post.assert_called_once_with(
                "/api/embeddings",
                json={
                    "model": "nomic-embed-text",
                    "prompt": "test text",
                },
            )

    @pytest.mark.asyncio
    async def test_embed_error_handling(self, ollama_config):
        """Embedding errors are handled correctly."""
        from src.glp.agent.providers.base import LLMProviderError
        import httpx

        # Don't patch httpx - we need real exception classes
        provider = OllamaProvider(ollama_config)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_request = MagicMock()

        # Create real httpx exception
        error = httpx.HTTPStatusError(
            "Error", request=mock_request, response=mock_response
        )
        mock_response.raise_for_status.side_effect = error
        mock_client.post = AsyncMock(return_value=mock_response)

        # Replace the provider's client
        provider.client = mock_client

        with pytest.raises(LLMProviderError, match="Ollama embedding API error"):
            await provider.embed("test")

    @pytest.mark.asyncio
    async def test_embed_empty_response(self, ollama_config):
        """Empty embedding response raises error."""
        from src.glp.agent.providers.base import LLMProviderError

        # Don't patch httpx - we need real exception classes
        provider = OllamaProvider(ollama_config)

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"embedding": []}  # Empty embedding
        mock_client.post = AsyncMock(return_value=mock_response)

        # Replace the provider's client
        provider.client = mock_client

        with pytest.raises(LLMProviderError, match="No embedding returned"):
            await provider.embed("test")


class TestOllamaContextManager:
    """Tests for async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager(self, ollama_config, mock_httpx_client):
        """Provider works as async context manager."""
        with patch("src.glp.agent.providers.ollama.httpx"):
            async with OllamaProvider(ollama_config) as provider:
                provider.client = mock_httpx_client
                assert provider is not None

            # Verify cleanup was called
            mock_httpx_client.aclose.assert_called_once()
