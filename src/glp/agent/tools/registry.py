"""
Tool Registry.

Provides a unified registry of all available tools (read and write)
for the agent chatbot. Handles tool discovery and execution routing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..domain.entities import ToolCall, ToolDefinition, UserContext
from ..domain.ports import IMCPClient, IToolExecutor

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Unified registry of all agent tools.

    Combines:
    - Read tools from MCP server (database queries)
    - Write tools from WriteExecutor (REST API mutations)

    Handles tool discovery, execution routing, and result aggregation.

    Usage:
        registry = ToolRegistry(mcp_client, write_executor)

        # Get all available tools
        tools = await registry.get_all_tools()

        # Execute a tool call
        result = await registry.execute_tool_call(tool_call, context)

    Architecture:
        - MCP tools are discovered dynamically from the server
        - Write tools are statically defined in WriteExecutor
        - Tool calls are routed based on is_read_only flag
    """

    def __init__(
        self,
        mcp_client: Optional[IMCPClient] = None,
        write_executor: Optional[IToolExecutor] = None,
    ):
        """Initialize the tool registry.

        Args:
            mcp_client: MCP client for read operations
            write_executor: Write executor for mutations
        """
        self.mcp_client = mcp_client
        self.write_executor = write_executor
        self._tools_cache: Optional[list[ToolDefinition]] = None

    async def get_all_tools(self, refresh: bool = False) -> list[ToolDefinition]:
        """Get all available tools.

        Combines MCP tools and write tools into a single list.

        Args:
            refresh: Force refresh of cached tools

        Returns:
            List of all tool definitions
        """
        if self._tools_cache and not refresh:
            return self._tools_cache

        tools: list[ToolDefinition] = []

        # Get MCP tools (read operations)
        if self.mcp_client:
            try:
                mcp_tools = await self.mcp_client.list_tools()
                tools.extend(mcp_tools)
                logger.info(f"Loaded {len(mcp_tools)} MCP tools")
            except Exception as e:
                logger.error(f"Failed to load MCP tools: {e}")

        # Get write tools
        if self.write_executor:
            try:
                write_tools = self.write_executor.get_tool_definitions()
                tools.extend(write_tools)
                logger.info(f"Loaded {len(write_tools)} write tools")
            except Exception as e:
                logger.error(f"Failed to load write tools: {e}")

        self._tools_cache = tools
        logger.info(f"Tool registry loaded {len(tools)} total tools")

        return tools

    async def get_read_tools(self) -> list[ToolDefinition]:
        """Get only read-only tools.

        Returns:
            List of read-only tool definitions
        """
        all_tools = await self.get_all_tools()
        return [t for t in all_tools if t.is_read_only]

    async def get_write_tools(self) -> list[ToolDefinition]:
        """Get only write tools.

        Returns:
            List of write tool definitions
        """
        all_tools = await self.get_all_tools()
        return [t for t in all_tools if not t.is_read_only]

    def is_write_tool(self, tool_name: str) -> bool:
        """Check if a tool is a write operation.

        Uses the cached tool definitions to determine if a tool is a write
        operation based on the is_read_only attribute. Falls back to checking
        the write_executor if the tool isn't in the cache.

        Args:
            tool_name: Tool name to check

        Returns:
            True if tool performs mutations
        """
        # Check cached tools first
        if self._tools_cache:
            for tool in self._tools_cache:
                if tool.name == tool_name:
                    return not tool.is_read_only

        # Fallback: check if write_executor has this tool
        if self.write_executor:
            try:
                write_tools = self.write_executor.get_tool_definitions()
                write_tool_names = {t.name for t in write_tools}
                return tool_name in write_tool_names
            except Exception:
                pass

        # Default to read-only (safer)
        return False

    async def execute_tool_call(
        self,
        tool_call: ToolCall,
        context: UserContext,
    ) -> ToolCall:
        """Execute a tool call and populate result.

        Routes to appropriate executor based on tool type.

        Args:
            tool_call: Tool call from LLM
            context: User context

        Returns:
            ToolCall with result populated
        """
        logger.debug(f"Executing tool: {tool_call.name}")

        if self.is_write_tool(tool_call.name):
            # Route to write executor
            if not self.write_executor:
                tool_call.result = {
                    "error": "Write operations not available",
                    "recoverable": False,
                }
                return tool_call

            return await self.write_executor.execute_tool_call(tool_call, context)

        else:
            # Route to MCP client (read operation)
            if not self.mcp_client:
                tool_call.result = {
                    "error": "Read operations not available",
                    "recoverable": False,
                }
                return tool_call

            return await self.mcp_client.execute_tool_call(tool_call, context)

    async def execute_tool_calls(
        self,
        tool_calls: list[ToolCall],
        context: UserContext,
    ) -> list[ToolCall]:
        """Execute multiple tool calls.

        Note: Executes sequentially to maintain order and handle dependencies.
        For parallel execution of independent tools, use execute_tool_call directly.

        Args:
            tool_calls: List of tool calls
            context: User context

        Returns:
            List of executed tool calls with results
        """
        results = []
        for tool_call in tool_calls:
            executed = await self.execute_tool_call(tool_call, context)
            results.append(executed)
        return results

    def get_tool_by_name(
        self, name: str, tools: list[ToolDefinition]
    ) -> Optional[ToolDefinition]:
        """Find a tool definition by name.

        Args:
            name: Tool name
            tools: List of tool definitions to search

        Returns:
            Tool definition if found
        """
        for tool in tools:
            if tool.name == name:
                return tool
        return None

    def clear_cache(self) -> None:
        """Clear the tools cache.

        Call this to force re-discovery of tools.
        """
        self._tools_cache = None


def get_all_tools() -> list[ToolDefinition]:
    """Get static list of all tool definitions.

    This is a synchronous helper for cases where async is not available.
    Returns only the write tools since MCP tools require async discovery.

    Returns:
        List of write tool definitions
    """
    from .write_executor import WriteExecutor

    # Create a temporary executor to get definitions
    # Note: This doesn't need a real device_manager since we're only
    # getting definitions, not executing
    class DummyDeviceManager:
        pass

    executor = WriteExecutor(DummyDeviceManager())  # type: ignore
    return executor.get_tool_definitions()


def format_tools_for_llm(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Format tool definitions for LLM consumption.

    Converts ToolDefinition objects to the format expected by LLM providers.

    Args:
        tools: List of tool definitions

    Returns:
        List of tool dicts in LLM format
    """
    formatted = []
    for tool in tools:
        formatted.append(tool.to_openai_format())
    return formatted


def format_tool_results_for_llm(tool_calls: list[ToolCall]) -> list[dict[str, Any]]:
    """Format tool call results for LLM consumption.

    Args:
        tool_calls: Executed tool calls with results

    Returns:
        List of result dicts for LLM
    """
    results = []
    for tc in tool_calls:
        results.append({
            "tool_call_id": tc.id,
            "name": tc.name,
            "result": tc.result,
        })
    return results
