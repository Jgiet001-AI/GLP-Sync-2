"""
FastAPI Router for Agent Chatbot.

Provides REST endpoints and WebSocket handler for the agent chatbot.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from ...api.error_sanitizer import sanitize_error_message
from ..domain.entities import UserContext
from ..orchestrator import AgentOrchestrator
from ..security import TicketAuth
from .auth import get_user_context_jwt
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConfirmationRequest,
    ConversationListItem,
    ConversationListResponse,
    ConversationResponse,
    MemoryStatsResponse,
    MessageResponse,
    TicketResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])


# =============================================================================
# Dependencies
# =============================================================================


class AgentDependencies:
    """Container for agent dependencies.

    Injected at application startup.
    """

    orchestrator: Optional[AgentOrchestrator] = None
    ticket_auth: Optional[TicketAuth] = None


_deps = AgentDependencies()


def create_agent_dependencies(
    orchestrator: AgentOrchestrator,
    ticket_auth: Optional[TicketAuth] = None,
) -> None:
    """Initialize agent dependencies.

    Call this at application startup.

    Args:
        orchestrator: The agent orchestrator
        ticket_auth: Optional ticket auth for WebSocket
    """
    _deps.orchestrator = orchestrator
    _deps.ticket_auth = ticket_auth


def get_orchestrator() -> AgentOrchestrator:
    """Get the agent orchestrator dependency."""
    if not _deps.orchestrator:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent not initialized",
        )
    return _deps.orchestrator


def get_user_context(
    context: UserContext = Depends(get_user_context_jwt),
) -> UserContext:
    """Get user context from validated JWT token.

    Uses JWT authentication instead of raw headers.
    The JWT is validated in get_user_context_jwt dependency.

    Security: Never trust raw headers - always validate JWT.
    """
    return context


# =============================================================================
# REST Endpoints
# =============================================================================


@router.post("/chat", response_model=ChatResponse)
async def start_chat(
    request: ChatRequest,
    context: UserContext = Depends(get_user_context),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> ChatResponse:
    """Start a new chat message.

    For real-time streaming, use the WebSocket endpoint instead.
    This endpoint initiates processing and returns immediately.
    """
    # Get or create conversation
    conversation = await orchestrator._get_or_create_conversation(
        request.conversation_id, context
    )

    # Process asynchronously (client should connect via WebSocket)
    task = asyncio.create_task(
        _process_chat_async(
            orchestrator,
            request.message,
            context,
            conversation.id,
        ),
        name=f"chat-{conversation.id}",
    )
    task.add_done_callback(_task_exception_handler)

    return ChatResponse(
        conversation_id=conversation.id,
        status="processing",
    )


def _task_exception_handler(task: asyncio.Task) -> None:
    """Handle exceptions from background tasks.

    Ensures exceptions are logged and don't cause unhandled exception warnings.
    """
    try:
        exc = task.exception()
        if exc:
            logger.error(
                f"Background task {task.get_name()} failed: {exc}",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
    except asyncio.CancelledError:
        pass  # Task was cancelled, not an error


async def _process_chat_async(
    orchestrator: AgentOrchestrator,
    message: str,
    context: UserContext,
    conversation_id: UUID,
) -> None:
    """Process chat asynchronously.

    Events are delivered via WebSocket.
    Note: This is used by the REST endpoint - errors are logged since
    the client should be connected via WebSocket to receive events.
    """
    try:
        async for event in orchestrator.chat(message, context, conversation_id):
            # Events are streamed via WebSocket
            pass
    except asyncio.CancelledError:
        logger.info(f"Chat processing cancelled for conversation {conversation_id}")
        raise
    except Exception as e:
        logger.exception(f"Async chat processing failed: {e}")


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: UserContext = Depends(get_user_context),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> ConversationListResponse:
    """List user's conversations."""
    conversations = await orchestrator.list_conversations(context, limit, offset)

    items = [
        ConversationListItem(
            id=c.id,
            title=c.title,
            summary=c.summary,
            message_count=c.message_count,
            last_message_preview=c.metadata.get("last_message_preview"),
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conversations
    ]

    return ConversationListResponse(
        conversations=items,
        total=len(items),  # Would need a count query for accurate total
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    context: UserContext = Depends(get_user_context),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> ConversationResponse:
    """Get a conversation with messages."""
    conversation = await orchestrator.get_conversation_history(
        conversation_id, context
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    messages = [
        MessageResponse(
            id=m.id,
            role=m.role.value,
            content=m.content,
            thinking_summary=m.thinking_summary,
            tool_calls=[
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments, "result": tc.result}
                for tc in (m.tool_calls or [])
            ] if m.tool_calls else None,
            model_used=m.model_used,
            tokens_used=m.tokens_used,
            created_at=m.created_at,
        )
        for m in conversation.messages
    ]

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        summary=conversation.summary,
        message_count=conversation.message_count,
        messages=messages,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    context: UserContext = Depends(get_user_context),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> None:
    """Delete a conversation."""
    if orchestrator.conversations:
        deleted = await orchestrator.conversations.delete(conversation_id, context)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )


@router.post("/confirm", status_code=status.HTTP_200_OK)
async def confirm_operation(
    request: ConfirmationRequest,
    context: UserContext = Depends(get_user_context),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> dict[str, Any]:
    """Confirm or cancel a pending write operation.

    For WebSocket clients, use the ws/confirm message instead.
    """
    # Find conversation with this pending operation
    for conv_id, ops in orchestrator._pending_confirmations.items():
        if str(request.operation_id) in ops:
            # Process confirmation
            events = []
            async for event in orchestrator.confirm_operation(
                conv_id, request.confirmed, context, str(request.operation_id)
            ):
                events.append(event.to_dict())

            return {
                "status": "confirmed" if request.confirmed else "cancelled",
                "events": events,
            }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Pending operation not found",
    )


@router.post("/ticket", response_model=TicketResponse)
async def get_websocket_ticket(
    context: UserContext = Depends(get_user_context),
) -> TicketResponse:
    """Get a one-time ticket for WebSocket connection.

    The ticket is valid for 60 seconds and can only be used once.
    """
    if not _deps.ticket_auth:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ticket auth not configured",
        )

    ticket = await _deps.ticket_auth.create_ticket(
        user_id=context.user_id,
        tenant_id=context.tenant_id,
        session_id=context.session_id or "default",
    )

    return TicketResponse(
        ticket=ticket,
        expires_in=60,
    )


@router.get("/memory/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    context: UserContext = Depends(get_user_context),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator),
) -> MemoryStatsResponse:
    """Get memory statistics for the user."""
    if not orchestrator.memory:
        return MemoryStatsResponse(total=0, active=0, by_type={})

    stats = await orchestrator.memory.get_stats(context)

    return MemoryStatsResponse(
        total=stats.get("total", 0),
        active=stats.get("active", 0),
        by_type=stats.get("by_type", {}),
    )


# =============================================================================
# WebSocket Handler
# =============================================================================


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: str = Query(..., description="One-time authentication ticket from /api/agent/ticket"),
):
    """WebSocket endpoint for streaming chat.

    Connection flow:
    1. Client authenticates via JWT and calls POST /api/agent/ticket
    2. Client connects to ws://host/api/agent/ws?ticket=XXX
    3. Server validates and consumes ticket (one-time use)
    4. Client sends messages, server streams events

    Security:
    - Ticket is REQUIRED - no header fallback
    - Ticket is one-time use and expires in 60 seconds
    - Ticket is bound to tenant/user from the JWT used to create it

    Message formats:
    - Client -> Server:
        {"type": "chat", "message": "...", "conversation_id": "..."}
        {"type": "confirm", "operation_id": "...", "confirmed": true/false}
        {"type": "cancel"}

    - Server -> Client:
        {"type": "text_delta", "content": "...", ...}
        {"type": "tool_call_start", "tool_name": "...", ...}
        {"type": "confirmation_required", "message": "...", ...}
        {"type": "done", ...}
        {"type": "error", "content": "...", ...}
    """
    # Ticket authentication is REQUIRED - no fallback
    if not _deps.ticket_auth:
        logger.error("WebSocket ticket auth not configured")
        await websocket.close(code=4003, reason="Ticket auth not configured")
        return

    # Validate and consume ticket (one-time use)
    ticket_data = await _deps.ticket_auth.validate_ticket(ticket)
    if not ticket_data:
        logger.warning("Invalid or expired WebSocket ticket")
        await websocket.close(code=4001, reason="Invalid or expired ticket")
        return

    # Convert ticket data to UserContext for the orchestrator
    context = UserContext(
        tenant_id=ticket_data.tenant_id,
        user_id=ticket_data.user_id,
        session_id=ticket_data.session_id,
    )

    # Accept connection
    await websocket.accept()
    logger.info(f"WebSocket connected: user={context.user_id}")

    orchestrator = _deps.orchestrator
    if not orchestrator:
        await websocket.send_json({
            "type": "error",
            "content": "Agent not initialized",
        })
        await websocket.close()
        return

    current_task: Optional[asyncio.Task] = None

    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                # Cancel any existing task
                if current_task and not current_task.done():
                    current_task.cancel()

                # Start new chat
                message = data.get("message", "")
                conversation_id = data.get("conversation_id")

                if conversation_id:
                    try:
                        conversation_id = UUID(conversation_id)
                    except ValueError:
                        conversation_id = None

                # Stream response
                current_task = asyncio.create_task(
                    _stream_chat(
                        websocket,
                        orchestrator,
                        message,
                        context,
                        conversation_id,
                    )
                )

            elif msg_type == "confirm":
                # Handle confirmation
                operation_id = data.get("operation_id")
                confirmed = data.get("confirmed", False)

                # Find conversation with this operation
                found = False
                for conv_id, ops in orchestrator._pending_confirmations.items():
                    if str(operation_id) in ops:
                        async for event in orchestrator.confirm_operation(
                            conv_id, confirmed, context, str(operation_id)
                        ):
                            await websocket.send_json(event.to_dict())
                        found = True
                        break

                if not found:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Pending operation not found",
                    })

            elif msg_type == "cancel":
                # Cancel current operation
                if current_task and not current_task.done():
                    current_task.cancel()
                    await websocket.send_json({
                        "type": "cancelled",
                        "content": "Operation cancelled",
                    })

            elif msg_type == "ping":
                # Heartbeat
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={context.user_id}")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        try:
            # Sanitize error message before sending to client
            sanitized = sanitize_error_message(str(e), "WebSocket error")
            await websocket.send_json({
                "type": "error",
                "content": sanitized,
            })
        except Exception:
            pass
    finally:
        if current_task and not current_task.done():
            current_task.cancel()


async def _stream_chat(
    websocket: WebSocket,
    orchestrator: AgentOrchestrator,
    message: str,
    context: UserContext,
    conversation_id: Optional[UUID],
) -> None:
    """Stream chat events to WebSocket.

    Args:
        websocket: WebSocket connection
        orchestrator: Agent orchestrator
        message: User message
        context: User context
        conversation_id: Optional conversation ID
    """
    try:
        async for event in orchestrator.chat(message, context, conversation_id):
            await websocket.send_json(event.to_dict())

    except asyncio.CancelledError:
        logger.info("Chat streaming cancelled")
        raise
    except Exception as e:
        logger.exception(f"Chat streaming error: {e}")
        # Sanitize error message before sending to client
        sanitized = sanitize_error_message(str(e), "Chat error")
        await websocket.send_json({
            "type": "error",
            "content": sanitized,
            "error_type": "fatal",
        })
