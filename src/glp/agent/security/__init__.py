"""Security components for the agent module."""

from .cot_redactor import CoTRedactor
from .ticket_auth import WebSocketTicket, WebSocketTicketAuth

# Alias for backward compatibility
TicketAuth = WebSocketTicketAuth

__all__ = [
    "CoTRedactor",
    "WebSocketTicket",
    "WebSocketTicketAuth",
    "TicketAuth",  # Alias
]
