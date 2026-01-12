"""
MCP Client for Read Operations.

Connects to the FastMCP server for read-only database operations.
Reuses existing audit logging and caching from the MCP server.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import aiohttp

from ..domain.entities import ToolCall, ToolDefinition, UserContext
from ..domain.ports import IMCPClient

logger = logging.getLogger(__name__)


class MCPToolError(Exception):
    """Error executing an MCP tool."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        recoverable: bool = True,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.tool_name = tool_name
        self.recoverable = recoverable
        self.original_error = original_error


@dataclass
class MCPClientConfig:
    """Configuration for MCP client."""

    # Server connection
    base_url: str = "http://localhost:8000"
    timeout: float = 30.0
    max_retries: int = 3

    # Authentication (service-to-service)
    service_api_key: Optional[str] = None

    # Request settings
    verify_ssl: bool = True


class MCPClient(IMCPClient):
    """Client for FastMCP server operations.

    Handles read-only database operations by calling the FastMCP server's
    HTTP transport. Provides tool discovery and execution.

    Usage:
        config = MCPClientConfig(base_url="http://mcp-server:8000")
        client = MCPClient(config)

        # List available tools
        tools = await client.list_tools()

        # Execute a tool
        result = await client.call_tool(
            "search_devices",
            {"query": "aruba 6200", "limit": 10},
            user_context,
        )

    Architecture:
        - Uses HTTP transport to connect to FastMCP server
        - Passes user context for audit logging on server side
        - Caches tool definitions for performance
    """

    # Cache TTL for tool definitions
    TOOL_CACHE_TTL_SECONDS = 300

    def __init__(self, config: MCPClientConfig):
        """Initialize the MCP client.

        Args:
            config: Client configuration
        """
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._tools_cache: Optional[list[ToolDefinition]] = None
        self._tools_cache_time: float = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the client session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_headers(self, context: Optional[UserContext] = None) -> dict[str, str]:
        """Build request headers with auth and context."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        # Service-to-service auth
        if self.config.service_api_key:
            headers["X-Service-Key"] = self.config.service_api_key

        # Pass user context for audit logging
        if context:
            headers["X-Tenant-ID"] = context.tenant_id
            headers["X-User-ID"] = context.user_id
            if context.session_id:
                headers["X-Session-ID"] = context.session_id

        return headers

    async def list_tools(self) -> list[ToolDefinition]:
        """List available tools from the MCP server.

        Caches results for TOOL_CACHE_TTL_SECONDS.

        Returns:
            List of tool definitions
        """
        import time

        # Check cache
        if self._tools_cache and (
            time.time() - self._tools_cache_time < self.TOOL_CACHE_TTL_SECONDS
        ):
            return self._tools_cache

        session = await self._get_session()
        url = f"{self.config.base_url}/mcp/v1/tools/list"

        try:
            async with session.post(
                url,
                headers=self._get_headers(),
                json={},
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise MCPToolError(
                        f"Failed to list tools: {response.status} - {text}",
                        tool_name="list_tools",
                    )

                data = await response.json()
                tools_data = data.get("tools", [])

                tools = []
                for tool_data in tools_data:
                    tool = ToolDefinition(
                        name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        parameters=tool_data.get("inputSchema", {}),
                        is_read_only=tool_data.get("annotations", {}).get(
                            "readOnlyHint", True
                        ),
                    )
                    tools.append(tool)

                # Update cache
                self._tools_cache = tools
                self._tools_cache_time = time.time()

                logger.info(f"Discovered {len(tools)} MCP tools")
                return tools

        except aiohttp.ClientError as e:
            raise MCPToolError(
                f"Failed to connect to MCP server: {e}",
                tool_name="list_tools",
                original_error=e,
            )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: UserContext,
    ) -> Any:
        """Execute a tool on the MCP server.

        Args:
            name: Tool name
            arguments: Tool arguments
            context: User context for audit

        Returns:
            Tool execution result

        Raises:
            MCPToolError: On execution failure
        """
        session = await self._get_session()
        url = f"{self.config.base_url}/mcp/v1/tools/call"

        payload = {
            "name": name,
            "arguments": arguments,
        }

        for attempt in range(self.config.max_retries):
            try:
                async with session.post(
                    url,
                    headers=self._get_headers(context),
                    json=payload,
                ) as response:
                    if response.status == 200:
                        data = await response.json()

                        # MCP returns content as array
                        content = data.get("content", [])
                        if content and len(content) > 0:
                            # Extract text content
                            first = content[0]
                            if first.get("type") == "text":
                                text = first.get("text", "")
                                # Try to parse as JSON
                                try:
                                    return json.loads(text)
                                except json.JSONDecodeError:
                                    return text

                        return content

                    elif response.status == 404:
                        raise MCPToolError(
                            f"Tool not found: {name}",
                            tool_name=name,
                            recoverable=False,
                        )

                    elif response.status == 429:
                        # Rate limited - retry with backoff
                        if attempt < self.config.max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(
                                f"Rate limited, retrying in {wait_time}s"
                            )
                            await asyncio.sleep(wait_time)
                            continue

                        raise MCPToolError(
                            "Rate limited by MCP server",
                            tool_name=name,
                        )

                    else:
                        text = await response.text()
                        raise MCPToolError(
                            f"Tool execution failed: {response.status} - {text}",
                            tool_name=name,
                        )

            except aiohttp.ClientError as e:
                if attempt < self.config.max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"Connection error, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue

                raise MCPToolError(
                    f"Failed to connect to MCP server: {e}",
                    tool_name=name,
                    original_error=e,
                )

        # Should not reach here
        raise MCPToolError(
            f"Tool execution failed after {self.config.max_retries} retries",
            tool_name=name,
        )

    async def execute_tool_call(
        self,
        tool_call: ToolCall,
        context: UserContext,
    ) -> ToolCall:
        """Execute a tool call and populate result.

        Convenience method that takes a ToolCall object.

        Args:
            tool_call: Tool call to execute
            context: User context

        Returns:
            ToolCall with result populated
        """
        try:
            result = await self.call_tool(
                tool_call.name,
                tool_call.arguments,
                context,
            )
            tool_call.result = result

        except MCPToolError as e:
            tool_call.result = {
                "error": str(e),
                "recoverable": e.recoverable,
            }

        return tool_call


class InProcessMCPClient(IMCPClient):
    """In-process MCP client for direct tool execution.

    Used when the agent runs in the same process as the MCP server.
    Bypasses HTTP overhead for better performance.

    Usage:
        from server import search_devices, list_devices

        tools = {
            "search_devices": search_devices,
            "list_devices": list_devices,
        }
        client = InProcessMCPClient(tools)
    """

    def __init__(self, tools: dict[str, Any]):
        """Initialize with tool functions.

        Args:
            tools: Dict mapping tool names to async functions
        """
        self.tools = tools

    async def list_tools(self) -> list[ToolDefinition]:
        """List available tools.

        Returns tool definitions from function docstrings.
        """
        definitions = []
        for name, func in self.tools.items():
            doc = func.__doc__ or ""
            definitions.append(
                ToolDefinition(
                    name=name,
                    description=doc.split("\n")[0] if doc else "",
                    parameters={},  # Would need inspection for full schema
                    is_read_only=True,
                )
            )
        return definitions

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: UserContext,
    ) -> Any:
        """Execute a tool directly.

        Args:
            name: Tool name
            arguments: Tool arguments
            context: User context (passed as ctx if function accepts it)

        Returns:
            Tool result
        """
        if name not in self.tools:
            raise MCPToolError(
                f"Tool not found: {name}",
                tool_name=name,
                recoverable=False,
            )

        func = self.tools[name]

        try:
            # Call the tool function
            result = await func(**arguments)
            return result

        except Exception as e:
            raise MCPToolError(
                f"Tool execution failed: {e}",
                tool_name=name,
                original_error=e,
            )

    async def execute_tool_call(
        self,
        tool_call: ToolCall,
        context: UserContext,
    ) -> ToolCall:
        """Execute a tool call."""
        try:
            result = await self.call_tool(
                tool_call.name,
                tool_call.arguments,
                context,
            )
            tool_call.result = result

        except MCPToolError as e:
            tool_call.result = {
                "error": str(e),
                "recoverable": e.recoverable,
            }

        return tool_call
