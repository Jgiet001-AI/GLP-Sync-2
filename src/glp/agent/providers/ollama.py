"""
Ollama LLM Provider.

Implements the ILLMProvider interface for Ollama's local LLM API.
Supports streaming chat and embeddings with locally-hosted models.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

from ..domain.entities import (
    ChatEvent,
    ChatEventType,
    ErrorType,
    Message,
    MessageRole,
    ToolDefinition,
)
from .base import BaseLLMProvider, LLMProviderConfig, LLMProviderError

logger = logging.getLogger(__name__)

# Lazy import to avoid requiring httpx if not used
try:
    import httpx

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    httpx = None


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider implementation.

    Supports:
    - Locally-hosted models (qwen, llama, mistral, etc.)
    - Streaming responses
    - Tool/function calling (if model supports it)
    - Embeddings

    Usage:
        config = LLMProviderConfig(
            api_key="not-needed",  # Ollama doesn't require auth
            model="qwen3:4b",
            base_url="http://localhost:11434",
        )
        provider = OllamaProvider(config)

        async for event in provider.chat(messages, tools):
            print(event)
    """

    # Default configuration
    DEFAULT_MODEL = "qwen3:4b"
    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"

    def __init__(self, config: LLMProviderConfig):
        """Initialize the Ollama provider.

        Args:
            config: Provider configuration

        Raises:
            ImportError: If httpx package is not installed
        """
        if not OLLAMA_AVAILABLE:
            raise ImportError(
                "httpx package is required for OllamaProvider. "
                "Install with: pip install httpx"
            )

        super().__init__(config)

        # Set defaults for Ollama
        self.base_url = config.base_url or self.DEFAULT_BASE_URL
        self.embedding_model = (
            config.embedding_model or self.DEFAULT_EMBEDDING_MODEL
        )

        # Initialize HTTP client
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=config.timeout,
        )

    @property
    def supports_tools(self) -> bool:
        """Some Ollama models support tool calling (e.g., qwen2.5, llama3.1)."""
        # Tool support varies by model - we'll try and handle errors gracefully
        return True

    def _format_messages_for_api(
        self, messages: list[Message], system_prompt: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Convert messages to Ollama format.

        Ollama uses OpenAI-compatible message format.
        """
        api_messages = []

        # Add system prompt first if provided
        if system_prompt:
            api_messages.append({
                "role": "system",
                "content": system_prompt,
            })

        for msg in messages:
            if msg.role == MessageRole.TOOL:
                # Tool results as user messages
                api_messages.append({
                    "role": "user",
                    "content": f"Tool result: {msg.content}",
                })
            elif msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                # Assistant message with tool calls
                tool_calls_text = "\n".join(
                    f"Calling {tc.name} with {json.dumps(tc.arguments)}"
                    for tc in msg.tool_calls
                )
                content = msg.content or ""
                if content and tool_calls_text:
                    content = f"{content}\n\n{tool_calls_text}"
                elif tool_calls_text:
                    content = tool_calls_text
                api_messages.append({
                    "role": "assistant",
                    "content": content,
                })
            else:
                api_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        return api_messages

    def _format_tools_for_api(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]]:
        """Convert tools to Ollama format.

        Ollama uses OpenAI-compatible tool format.
        """
        return [tool.to_openai_format() for tool in tools]

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Generate a streaming response using Ollama.

        Args:
            messages: Conversation history
            tools: Available tools (optional, model-dependent)
            system_prompt: System prompt
            stream: Whether to stream (always True for this implementation)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Yields:
            ChatEvent objects
        """
        self._reset_sequence()

        # Format messages
        api_messages = self._format_messages_for_api(messages, system_prompt)

        # Build request payload
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        # Only include tools if provided and model might support them
        if tools:
            payload["tools"] = self._format_tools_for_api(tools)

        try:
            # Make streaming request to Ollama API
            async with self.client.stream(
                "POST",
                "/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()

                # Process newline-delimited JSON stream
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse Ollama response: {e}")
                        continue

                    # Handle different response types
                    if chunk.get("done"):
                        # Stream complete
                        yield self._create_done()
                        break

                    # Extract message content
                    message = chunk.get("message", {})
                    content = message.get("content", "")

                    if content:
                        # Yield text delta
                        yield self._create_text_delta(content)

                    # Handle tool calls if present
                    tool_calls = message.get("tool_calls", [])
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        tool_args = tool_call.get("function", {}).get("arguments", {})
                        tool_id = tool_call.get("id", f"tool_{self._next_sequence()}")

                        if tool_name:
                            yield self._create_tool_call_start(tool_id, tool_name)
                            if tool_args:
                                if isinstance(tool_args, str):
                                    try:
                                        tool_args = json.loads(tool_args)
                                    except json.JSONDecodeError:
                                        tool_args = {}
                                yield self._create_tool_call_end(tool_id, tool_args)

        except httpx.HTTPStatusError as e:
            error_msg = f"Ollama API error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            yield self._create_error(error_msg, ErrorType.RECOVERABLE)
            yield self._create_done()

        except httpx.TimeoutException as e:
            error_msg = f"Ollama request timeout: {str(e)}"
            logger.error(error_msg)
            yield self._create_error(error_msg, ErrorType.TIMEOUT)
            yield self._create_done()

        except httpx.RequestError as e:
            error_msg = f"Ollama connection error: {str(e)}"
            logger.error(error_msg)
            yield self._create_error(error_msg, ErrorType.FATAL)
            yield self._create_done()

        except Exception as e:
            error_msg = f"Unexpected error in Ollama provider: {str(e)}"
            logger.exception(error_msg)
            yield self._create_error(error_msg, ErrorType.FATAL)
            yield self._create_done()

    async def embed(self, text: str) -> tuple[list[float], str, int]:
        """Generate an embedding using Ollama.

        Args:
            text: Text to embed

        Returns:
            Tuple of (embedding_vector, model_name, dimension)

        Raises:
            LLMProviderError: If embedding generation fails
        """
        try:
            # Call Ollama embeddings API
            response = await self.client.post(
                "/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": text,
                },
            )
            response.raise_for_status()

            data = response.json()
            embedding = data.get("embedding", [])

            if not embedding:
                raise LLMProviderError(
                    "No embedding returned from Ollama",
                    error_type=ErrorType.RECOVERABLE,
                )

            return (
                embedding,
                self.embedding_model,
                len(embedding),
            )

        except httpx.HTTPStatusError as e:
            raise LLMProviderError(
                f"Ollama embedding API error: {e.response.status_code} - {e.response.text}",
                error_type=ErrorType.RECOVERABLE,
                original_error=e,
            )

        except httpx.TimeoutException as e:
            raise LLMProviderError(
                f"Ollama embedding timeout: {str(e)}",
                error_type=ErrorType.TIMEOUT,
                original_error=e,
            )

        except httpx.RequestError as e:
            raise LLMProviderError(
                f"Ollama connection error: {str(e)}",
                error_type=ErrorType.FATAL,
                original_error=e,
            )

        except Exception as e:
            raise LLMProviderError(
                f"Unexpected error generating embedding: {str(e)}",
                error_type=ErrorType.FATAL,
                original_error=e,
            )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup client."""
        await self.client.aclose()
