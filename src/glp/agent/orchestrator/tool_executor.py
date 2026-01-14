"""
Tool Executor.

Handles execution of tool calls with error handling and result processing.
Coordinates with ToolRegistry to route tool calls to appropriate executors.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from ..domain.entities import ToolCall, UserContext
from ..tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Executes tool calls with error handling.

    Provides a wrapper around ToolRegistry to execute tool calls with
    proper error handling, logging, and result processing. Ensures
    that tool execution errors are caught and returned as recoverable
    errors rather than propagating exceptions.

    Usage:
        executor = ToolExecutor(tool_registry)

        result = await executor.execute_tool_call(
            tool_call,
            context,
            conversation_id
        )

    Architecture:
        - Delegates to ToolRegistry for actual execution
        - Catches all exceptions and converts to recoverable errors
        - Logs execution start, success, and failures
        - Ensures ToolCall always has a result (success or error)
    """

    def __init__(self, tool_registry: ToolRegistry):
        """Initialize the tool executor.

        Args:
            tool_registry: Registry for tool discovery and execution
        """
        self.tools = tool_registry

    async def execute_tool_call(
        self,
        tool_call: ToolCall,
        context: UserContext,
        conversation_id: UUID,
    ) -> ToolCall:
        """Execute a tool call with error handling.

        Routes the tool call to the appropriate executor via ToolRegistry.
        Catches all exceptions and converts them to recoverable errors
        in the ToolCall result.

        Args:
            tool_call: Tool call to execute
            context: User context for authorization and tracking
            conversation_id: Current conversation ID for logging

        Returns:
            ToolCall with result populated (either success or error)
        """
        logger.info(f"Executing tool: {tool_call.name}")

        try:
            result = await self.tools.execute_tool_call(tool_call, context)
            logger.debug(f"Tool {tool_call.name} result: {result.result}")
            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            tool_call.result = {
                "error": str(e),
                "recoverable": True,
            }
            return tool_call

    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        context: UserContext,
        conversation_id: UUID,
    ) -> list[ToolCall]:
        """Execute multiple tool calls sequentially.

        Executes each tool call in order, handling errors for each individually.
        A failed tool call does not stop execution of subsequent tools.

        Args:
            tool_calls: List of tool calls to execute
            context: User context for authorization and tracking
            conversation_id: Current conversation ID for logging

        Returns:
            List of ToolCalls with results populated
        """
        results = []
        for tool_call in tool_calls:
            result = await self.execute_tool_call(tool_call, context, conversation_id)
            results.append(result)

        return results
