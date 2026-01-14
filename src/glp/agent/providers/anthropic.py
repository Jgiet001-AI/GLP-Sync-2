"""
Anthropic Claude LLM Provider.

Implements the ILLMProvider interface for Anthropic's Claude models.
Supports streaming, tool calling, and extended thinking (CoT).
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
from ..security.cot_redactor import redact_cot
from .base import BaseLLMProvider, LLMProviderConfig, LLMProviderError

logger = logging.getLogger(__name__)

# Lazy import to avoid requiring anthropic if not used
try:
    import anthropic
    from anthropic import AsyncAnthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    anthropic = None
    AsyncAnthropic = None


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider implementation.

    Supports:
    - Claude 3 models (opus, sonnet, haiku)
    - Claude 3.5 models
    - Streaming responses
    - Tool/function calling
    - Extended thinking (CoT)

    Usage:
        config = LLMProviderConfig(
            api_key="sk-ant-...",
            model="claude-sonnet-4-20250514",
        )
        provider = AnthropicProvider(config)

        async for event in provider.chat(messages, tools):
            print(event)
    """

    # Default models
    DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
    DEFAULT_EMBEDDING_MODEL = "voyage-3"  # Anthropic recommends Voyage for embeddings

    # Model capabilities
    MODELS_WITH_THINKING = {
        "claude-3-opus-20240229",
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-sonnet-4-5-20250929",
    }

    def __init__(self, config: LLMProviderConfig):
        """Initialize the Anthropic provider.

        Args:
            config: Provider configuration

        Raises:
            ImportError: If anthropic package is not installed
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "anthropic package is required for AnthropicProvider. "
                "Install with: pip install anthropic"
            )

        super().__init__(config)

        # Initialize client
        self.client = AsyncAnthropic(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
        )

        # Check if model supports extended thinking
        self._supports_thinking = config.model in self.MODELS_WITH_THINKING

    @property
    def supports_tools(self) -> bool:
        """Claude 3+ models support tool calling."""
        return True

    def _format_messages_for_api(
        self, messages: list[Message], system_prompt: Optional[str] = None
    ) -> tuple[Optional[str], list[dict[str, Any]]]:
        """Convert messages to Anthropic format.

        Anthropic uses a separate system parameter, not in messages.

        Returns:
            Tuple of (system_prompt, messages_list)
        """
        api_messages = []
        system = system_prompt

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                # Prepend to system prompt
                if system:
                    system = f"{msg.content}\n\n{system}"
                else:
                    system = msg.content
            elif msg.role == MessageRole.TOOL:
                # Tool results need special formatting
                api_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_calls[0].id if msg.tool_calls else "unknown",
                            "content": msg.content,
                        }
                    ],
                })
            elif msg.role == MessageRole.ASSISTANT:
                # Assistant messages with tool calls need special formatting
                if msg.tool_calls:
                    content_blocks = []
                    # Add text content if present
                    if msg.content:
                        content_blocks.append({"type": "text", "text": msg.content})
                    # Add tool_use blocks
                    for tc in msg.tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                    api_messages.append({
                        "role": "assistant",
                        "content": content_blocks,
                    })
                else:
                    api_messages.append({
                        "role": "assistant",
                        "content": msg.content,
                    })
            else:
                api_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        return system, api_messages

    def _format_tools_for_api(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]]:
        """Convert tools to Anthropic format."""
        return [tool.to_anthropic_format() for tool in tools]

    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Generate a streaming response using Claude.

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
        system, api_messages = self._format_messages_for_api(messages, system_prompt)

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": api_messages,
        }

        # Enable extended thinking if supported and configured
        if self._supports_thinking and self.config.enable_thinking:
            thinking_budget = self.config.thinking_budget
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            kwargs["temperature"] = 1  # Required for extended thinking
            # max_tokens must be greater than thinking budget
            kwargs["max_tokens"] = max(thinking_budget + 4096, max_tokens or 0)
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens or self.config.max_tokens

        if system:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = self._format_tools_for_api(tools)

        try:
            async with self.client.messages.stream(**kwargs) as stream_response:
                current_tool_call_id: Optional[str] = None
                current_tool_name: Optional[str] = None
                accumulated_tool_input = ""
                accumulated_thinking = ""

                async for event in stream_response:
                    # Handle different event types
                    if hasattr(event, "type"):
                        if event.type == "content_block_start":
                            block = event.content_block
                            if hasattr(block, "type"):
                                if block.type == "tool_use":
                                    current_tool_call_id = block.id
                                    current_tool_name = block.name
                                    accumulated_tool_input = ""
                                    yield self._create_tool_call_start(
                                        block.id, block.name
                                    )
                                elif block.type == "thinking":
                                    accumulated_thinking = ""

                        elif event.type == "content_block_delta":
                            delta = event.delta
                            if hasattr(delta, "type"):
                                if delta.type == "text_delta":
                                    yield self._create_text_delta(delta.text)
                                elif delta.type == "input_json_delta":
                                    accumulated_tool_input += delta.partial_json
                                elif delta.type == "thinking_delta":
                                    accumulated_thinking += delta.thinking
                                    # Redact and yield thinking
                                    redacted = redact_cot(delta.thinking)
                                    if redacted:
                                        yield self._create_thinking_delta(redacted)

                        elif event.type == "content_block_stop":
                            if current_tool_call_id:
                                # Parse accumulated tool input
                                try:
                                    arguments = json.loads(accumulated_tool_input) if accumulated_tool_input else {}
                                except json.JSONDecodeError:
                                    arguments = {"raw": accumulated_tool_input}

                                yield self._create_tool_call_end(
                                    current_tool_call_id, arguments
                                )
                                current_tool_call_id = None
                                current_tool_name = None

                yield self._create_done()

        except anthropic.RateLimitError as e:
            logger.warning(f"Rate limited by Anthropic: {e}")
            yield self._create_error(
                f"Rate limited: {e}", ErrorType.RATE_LIMIT
            )
        except anthropic.APITimeoutError as e:
            logger.error(f"Anthropic API timeout: {e}")
            yield self._create_error(
                f"Request timed out: {e}", ErrorType.TIMEOUT
            )
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            yield self._create_error(
                f"API error: {e}", ErrorType.RECOVERABLE
            )
        except Exception as e:
            logger.exception(f"Unexpected error in Anthropic chat: {e}")
            yield self._create_error(str(e), ErrorType.FATAL)

    async def embed(self, text: str) -> tuple[list[float], str, int]:
        """Generate an embedding for text.

        Note: Anthropic doesn't have native embeddings. This uses Voyage AI
        which Anthropic recommends. You'll need the voyageai package.

        For now, raises NotImplementedError - use OpenAI embeddings instead
        or implement Voyage AI integration.

        Args:
            text: Text to embed

        Returns:
            Tuple of (embedding_vector, model_name, dimension)

        Raises:
            NotImplementedError: Anthropic doesn't have native embeddings
        """
        # TODO: Implement Voyage AI embeddings or use a different provider
        raise NotImplementedError(
            "Anthropic doesn't provide native embeddings. "
            "Use OpenAI embeddings or implement Voyage AI integration."
        )

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the client."""
        await self.client.close()
