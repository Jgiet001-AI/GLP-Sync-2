"""
Pydantic schemas for agent API.

Defines request/response models for the chatbot API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Constants
# =============================================================================

MAX_MESSAGE_LENGTH = 10000


# =============================================================================
# Chat Schemas
# =============================================================================


class ChatRequest(BaseModel):
    """Request to send a chat message."""

    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    conversation_id: Optional[UUID] = None

    class Config:
        json_schema_extra = {
            "example": {
                "message": "Find all switches in the us-west region",
                "conversation_id": None,
            }
        }


class ChatResponse(BaseModel):
    """Response after initiating a chat.

    The actual response comes via WebSocket streaming.
    This response confirms the request was accepted.
    """

    conversation_id: UUID
    status: str = "processing"

    class Config:
        json_schema_extra = {
            "example": {
                "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "processing",
            }
        }


# =============================================================================
# Conversation Schemas
# =============================================================================


class MessageResponse(BaseModel):
    """A message in a conversation."""

    id: UUID
    role: str
    content: str
    thinking_summary: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    created_at: datetime


class ConversationResponse(BaseModel):
    """Response for a single conversation."""

    id: UUID
    title: Optional[str] = None
    summary: Optional[str] = None
    message_count: int
    messages: list[MessageResponse] = []
    created_at: datetime
    updated_at: datetime


class ConversationListItem(BaseModel):
    """Summary of a conversation for listing."""

    id: UUID
    title: Optional[str] = None
    summary: Optional[str] = None
    message_count: int
    last_message_preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Response for listing conversations."""

    conversations: list[ConversationListItem]
    total: int
    limit: int
    offset: int


# =============================================================================
# Confirmation Schemas
# =============================================================================


class ConfirmationRequest(BaseModel):
    """Request to confirm or cancel a pending operation."""

    operation_id: UUID
    confirmed: bool

    class Config:
        json_schema_extra = {
            "example": {
                "operation_id": "550e8400-e29b-41d4-a716-446655440000",
                "confirmed": True,
            }
        }


# =============================================================================
# Ticket Auth Schemas
# =============================================================================


class TicketRequest(BaseModel):
    """Request for a WebSocket connection ticket."""

    # No body needed - ticket is generated from auth context
    pass


class TicketResponse(BaseModel):
    """Response with WebSocket connection ticket."""

    ticket: str
    expires_in: int = Field(default=60, description="Seconds until expiration")

    class Config:
        json_schema_extra = {
            "example": {
                "ticket": "abc123...",
                "expires_in": 60,
            }
        }


# =============================================================================
# WebSocket Event Schemas
# =============================================================================


class WebSocketEvent(BaseModel):
    """WebSocket event sent to client."""

    type: str
    sequence: int
    correlation_id: Optional[str] = None
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    tool_arguments: Optional[dict[str, Any]] = None
    error_type: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "type": "text_delta",
                "sequence": 1,
                "content": "I found 15 switches in the us-west region...",
                "timestamp": "2024-01-15T10:30:00Z",
            }
        }


# =============================================================================
# Memory Schemas
# =============================================================================


class MemoryResponse(BaseModel):
    """Response for a memory item."""

    id: UUID
    memory_type: str
    content: str
    confidence: float
    created_at: datetime


class MemoryStatsResponse(BaseModel):
    """Response for memory statistics."""

    total: int
    active: int
    by_type: dict[str, dict[str, Any]]
