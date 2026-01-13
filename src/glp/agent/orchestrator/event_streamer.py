"""
Event Streamer for ChatEvent creation and streaming.

Manages event sequence state and creates ChatEvent objects with
auto-incrementing sequence numbers and correlation IDs for
distributed tracing.

Extracted from AgentOrchestrator to separate streaming event
management from orchestration logic.
"""

from __future__ import annotations

from typing import Any, Optional

from ..domain.entities import ChatEvent, ChatEventType, ErrorType


class EventStreamer:
    """Manages ChatEvent creation with sequence tracking.

    Handles:
    - Auto-incrementing sequence numbers
    - Correlation ID propagation for distributed tracing
    - Event creation with proper typing
    - Event state management

    Usage:
        streamer = EventStreamer(correlation_id=context.session_id)

        # Create events with auto-incrementing sequence
        event1 = streamer.create_event(ChatEventType.TEXT_DELTA, content="Hello")
        # sequence = 1

        event2 = streamer.create_event(ChatEventType.TEXT_DELTA, content=" world")
        # sequence = 2

        # Reset sequence for new conversation turn
        streamer.reset()
    """

    def __init__(self, correlation_id: Optional[str] = None):
        """Initialize the event streamer.

        Args:
            correlation_id: Optional correlation ID for request tracing
                          (typically context.session_id or context.request_id)
        """
        self.correlation_id = correlation_id
        self._sequence = 0

    def create_event(
        self,
        event_type: ChatEventType,
        content: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_arguments: Optional[dict[str, Any]] = None,
        confirmation_id: Optional[str] = None,
        error: Optional[str] = None,
        error_type: Optional[ErrorType] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ChatEvent:
        """Create a ChatEvent with auto-incrementing sequence.

        Args:
            event_type: Type of event (TEXT_DELTA, TOOL_CALL_START, etc.)
            content: Text content for TEXT_DELTA, THINKING_DELTA, etc.
            tool_call_id: Tool call ID for TOOL_CALL_* events
            tool_name: Tool name for TOOL_CALL_START
            tool_arguments: Tool arguments for TOOL_CALL_END
            confirmation_id: Confirmation ID for CONFIRMATION_* events
            error: Error message for ERROR events
            error_type: Type of error (RECOVERABLE, FATAL, etc.)
            metadata: Additional event metadata
            **kwargs: Additional fields to pass to ChatEvent

        Returns:
            ChatEvent with incremented sequence number
        """
        self._sequence += 1

        return ChatEvent(
            type=event_type,
            sequence=self._sequence,
            correlation_id=self.correlation_id,
            content=content,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_arguments=tool_arguments,
            confirmation_id=confirmation_id,
            error=error,
            error_type=error_type,
            metadata=metadata,
            **kwargs,
        )

    def reset(self) -> None:
        """Reset the sequence counter.

        Useful for:
        - Starting a new conversation turn
        - Resetting after errors
        - Testing scenarios
        """
        self._sequence = 0

    @property
    def sequence(self) -> int:
        """Get the current sequence number.

        Returns:
            Current sequence value (before next increment)
        """
        return self._sequence

    def set_correlation_id(self, correlation_id: Optional[str]) -> None:
        """Update the correlation ID.

        Useful when the correlation ID changes mid-stream
        (e.g., session handoff, request ID propagation).

        Args:
            correlation_id: New correlation ID
        """
        self.correlation_id = correlation_id
