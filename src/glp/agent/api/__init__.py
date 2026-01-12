"""Agent API layer.

Provides FastAPI router and WebSocket handler for the agent chatbot.
"""

from .router import router, create_agent_dependencies
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationResponse,
    ConfirmationRequest,
    TicketRequest,
    TicketResponse,
)

__all__ = [
    "router",
    "create_agent_dependencies",
    "ChatRequest",
    "ChatResponse",
    "ConversationListResponse",
    "ConversationResponse",
    "ConfirmationRequest",
    "TicketRequest",
    "TicketResponse",
]
