"""
Base LLM Provider Implementation.

Provides common functionality for all LLM providers.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from ..domain.entities import (
    ChatEvent,
    ChatEventType,
    ErrorType,
    Message,
    ToolDefinition,
)
from ..domain.ports import ILLMProvider

logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""

    def __init__(
        self,
        message: str,
        error_type: ErrorType = ErrorType.RECOVERABLE,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.original_error = original_error


@dataclass
class LLMProviderConfig:
    """Configuration for LLM providers.

    Attributes:
        api_key: API key for the provider
        model: Model name to use
        embedding_model: Model for embeddings (if different)
        base_url: Optional custom base URL
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        temperature: Default temperature
        max_tokens: Default max tokens
    """

    api_key: str
    model: str
    embedding_model: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 3
    temperature: float = 0.7
    max_tokens: int = 4096
    extra: dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ILLMProvider, ABC):
    """Base class for LLM provider implementations.

    Provides common functionality like error handling and retries.
    Subclasses must implement the abstract methods for specific APIs.
    """

    def __init__(self, config: LLMProviderConfig):
        """Initialize the provider.

        Args:
            config: Provider configuration
        """
        self.config = config
        self._sequence_counter = 0

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self.config.model

    @property
    def supports_streaming(self) -> bool:
        """Most modern providers support streaming."""
        return True

    @property
    def supports_tools(self) -> bool:
        """Most modern providers support tool calling."""
        return True

    def _next_sequence(self) -> int:
        """Get the next sequence number for events."""
        self._sequence_counter += 1
        return self._sequence_counter

    def _reset_sequence(self) -> None:
        """Reset the sequence counter (call at start of new chat)."""
        self._sequence_counter = 0

    def _create_text_delta(self, text: str) -> ChatEvent:
        """Create a text delta event."""
        return ChatEvent(
            type=ChatEventType.TEXT_DELTA,
            sequence=self._next_sequence(),
            content=text,
        )

    def _create_thinking_delta(self, text: str) -> ChatEvent:
        """Create a thinking delta event."""
        return ChatEvent(
            type=ChatEventType.THINKING_DELTA,
            sequence=self._next_sequence(),
            content=text,
        )

    def _create_tool_call_start(self, tool_call_id: str, name: str) -> ChatEvent:
        """Create a tool call start event."""
        return ChatEvent(
            type=ChatEventType.TOOL_CALL_START,
            sequence=self._next_sequence(),
            tool_call_id=tool_call_id,
            tool_name=name,
        )

    def _create_tool_call_end(self, tool_call_id: str, arguments: dict) -> ChatEvent:
        """Create a tool call end event."""
        return ChatEvent(
            type=ChatEventType.TOOL_CALL_END,
            sequence=self._next_sequence(),
            tool_call_id=tool_call_id,
            tool_arguments=arguments,
        )

    def _create_error(self, message: str, error_type: ErrorType) -> ChatEvent:
        """Create an error event."""
        return ChatEvent(
            type=ChatEventType.ERROR,
            sequence=self._next_sequence(),
            content=message,
            error=message,
            error_type=error_type,
        )

    def _create_done(self) -> ChatEvent:
        """Create a done event."""
        return ChatEvent(
            type=ChatEventType.DONE,
            sequence=self._next_sequence(),
        )

    def _format_messages_for_api(
        self, messages: list[Message]
    ) -> list[dict[str, Any]]:
        """Convert domain messages to API format.

        Subclasses may override for provider-specific formatting.
        """
        result = []
        for msg in messages:
            api_msg = {
                "role": msg.role.value,
                "content": msg.content,
            }
            result.append(api_msg)
        return result

    def _format_tools_for_api(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]]:
        """Convert tool definitions to API format.

        Subclasses should override for provider-specific formatting.
        """
        raise NotImplementedError("Subclass must implement _format_tools_for_api")

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: Optional[list[ToolDefinition]] = None,
        system_prompt: Optional[str] = None,
        stream: bool = True,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[ChatEvent]:
        """Generate a response. Must be implemented by subclasses."""
        pass

    @abstractmethod
    async def embed(self, text: str) -> tuple[list[float], str, int]:
        """Generate an embedding. Must be implemented by subclasses."""
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
