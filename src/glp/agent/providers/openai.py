"""
OpenAI GPT LLM Provider.

Implements the ILLMProvider interface for OpenAI's GPT models.
Supports streaming, tool calling, and embeddings.
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

# Lazy import to avoid requiring openai if not used
try:
    import openai
    from openai import AsyncOpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    openai = None
    AsyncOpenAI = None


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider implementation.

    Supports:
    - GPT-4, GPT-4 Turbo, GPT-4o
    - GPT-3.5 Turbo
    - Streaming responses
    - Tool/function calling
    - Embeddings (text-embedding-3-small/large)

    Usage:
        config = LLMProviderConfig(
            api_key="sk-...",
            model="gpt-4o",
            embedding_model="text-embedding-3-large",
        )
        provider = OpenAIProvider(config)

        async for event in provider.chat(messages, tools):
            print(event)
    """

    # Default models
    DEFAULT_MODEL = "gpt-5-nano-2025-08-07"
    DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"

    # Embedding dimensions by model
    EMBEDDING_DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, config: LLMProviderConfig):
        """Initialize the OpenAI provider.

        Args:
            config: Provider configuration

        Raises:
            ImportError: If openai package is not installed
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package is required for OpenAIProvider. "
                "Install with: pip install openai"
            )

        super().__init__(config)

        # Set embedding model
        self.embedding_model = (
            config.embedding_model or self.DEFAULT_EMBEDDING_MODEL
        )

        # Initialize client
        self.client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

    @property
    def supports_tools(self) -> bool:
        """GPT-4 and GPT-3.5-turbo support function calling."""
        return True

    def _format_messages_for_api(
        self, messages: list[Message], system_prompt: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Convert messages to OpenAI format.

        OpenAI includes system messages in the messages array.
        """
        api_messages = []

        # Add system prompt first
        if system_prompt:
            api_messages.append({
                "role": "system",
                "content": system_prompt,
            })

        for msg in messages:
            if msg.role == MessageRole.TOOL:
                # Tool results need special formatting
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_calls[0].id if msg.tool_calls else "unknown",
                    "content": msg.content,
                })
            elif msg.role == MessageRole.ASSISTANT and msg.tool_calls:
                # Assistant message with tool calls
                api_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
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
        """Convert tools to OpenAI format."""
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
        """Generate a streaming response using GPT.

        Args:
            messages: Conversation history
            tools: Available tools
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

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if tools:
            kwargs["tools"] = self._format_tools_for_api(tools)
            kwargs["tool_choice"] = "auto"

        try:
            stream_response = await self.client.chat.completions.create(**kwargs)

            # Track tool calls being assembled
            tool_calls_in_progress: dict[int, dict[str, Any]] = {}

            async for chunk in stream_response:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                delta = choice.delta

                # Handle text content
                if delta.content:
                    yield self._create_text_delta(delta.content)

                # Handle tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index

                        if idx not in tool_calls_in_progress:
                            # New tool call starting
                            tool_calls_in_progress[idx] = {
                                "id": tc.id or f"call_{idx}",
                                "name": tc.function.name if tc.function else "",
                                "arguments": "",
                            }
                            if tc.function and tc.function.name:
                                yield self._create_tool_call_start(
                                    tool_calls_in_progress[idx]["id"],
                                    tc.function.name,
                                )

                        # Accumulate arguments
                        if tc.function and tc.function.arguments:
                            tool_calls_in_progress[idx]["arguments"] += tc.function.arguments

                # Check for finish reason
                if choice.finish_reason:
                    # Emit any completed tool calls
                    for tc_data in tool_calls_in_progress.values():
                        try:
                            arguments = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                        except json.JSONDecodeError:
                            arguments = {"raw": tc_data["arguments"]}

                        yield self._create_tool_call_end(tc_data["id"], arguments)

                    break

            yield self._create_done()

        except openai.RateLimitError as e:
            logger.warning(f"Rate limited by OpenAI: {e}")
            yield self._create_error(
                f"Rate limited: {e}", ErrorType.RATE_LIMIT
            )
        except openai.APITimeoutError as e:
            logger.error(f"OpenAI API timeout: {e}")
            yield self._create_error(
                f"Request timed out: {e}", ErrorType.TIMEOUT
            )
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            yield self._create_error(
                f"API error: {e}", ErrorType.RECOVERABLE
            )
        except Exception as e:
            logger.exception(f"Unexpected error in OpenAI chat: {e}")
            yield self._create_error(str(e), ErrorType.FATAL)

    async def embed(self, text: str) -> tuple[list[float], str, int]:
        """Generate an embedding for text.

        Args:
            text: Text to embed

        Returns:
            Tuple of (embedding_vector, model_name, dimension)

        Raises:
            LLMProviderError: On API errors
        """
        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=text,
            )

            embedding = response.data[0].embedding
            dimension = len(embedding)

            return embedding, self.embedding_model, dimension

        except openai.RateLimitError as e:
            logger.warning(f"Rate limited during embedding: {e}")
            raise LLMProviderError(
                f"Rate limited: {e}",
                error_type=ErrorType.RATE_LIMIT,
                original_error=e,
            )
        except openai.APIError as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise LLMProviderError(
                f"Embedding failed: {e}",
                error_type=ErrorType.RECOVERABLE,
                original_error=e,
            )

    async def embed_batch(self, texts: list[str]) -> list[tuple[list[float], str, int]]:
        """Generate embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            List of (embedding_vector, model_name, dimension) tuples
        """
        if not texts:
            return []

        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )

            results = []
            for item in response.data:
                embedding = item.embedding
                dimension = len(embedding)
                results.append((embedding, self.embedding_model, dimension))

            return results

        except openai.APIError as e:
            logger.error(f"OpenAI batch embedding error: {e}")
            raise LLMProviderError(
                f"Batch embedding failed: {e}",
                error_type=ErrorType.RECOVERABLE,
                original_error=e,
            )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the client."""
        await self.client.close()
