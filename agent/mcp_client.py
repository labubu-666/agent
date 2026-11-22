"""Connects to MCP servers and runs their tool calls on a background event loop.

`Agent` is synchronous, so the MCP client (which is async) lives on its own thread.
Each server gets one task that owns its client for the whole session, because the
MCP client must be entered and exited in the same task.
"""

import asyncio
import concurrent.futures
import threading
from typing import Any

import structlog
from mcp import Client, StdioServerParameters, types

from .mcp_config import MCPServerConfig

logger = structlog.get_logger(__name__)

CONNECT_TIMEOUT_SECONDS = 30.0
CALL_TIMEOUT_SECONDS = 120.0
SHUTDOWN_TIMEOUT_SECONDS = 10.0


class MCPToolError(Exception):
    """Raised when a call to an MCP server tool cannot be completed."""


def _transport_for(config: MCPServerConfig) -> StdioServerParameters | str:
    if config.url is not None:
        return config.url
    return StdioServerParameters(
        command=config.command or "", args=config.args, env=config.env
    )


class MCPConnectionManager:
    """Starts the configured MCP servers and forwards tool calls to them."""

    def __init__(
        self,
        servers: dict[str, MCPServerConfig],
        connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
        call_timeout: float = CALL_TIMEOUT_SECONDS,
    ):
        self.servers = servers
        self.connect_timeout = connect_timeout
        self.call_timeout = call_timeout
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._loop.run_forever, name="mcp-event-loop", daemon=True
        )
        self._stop = asyncio.Event()
        self._clients: dict[str, Client] = {}
        self._serving: dict[str, concurrent.futures.Future[Any]] = {}

    def start(self) -> list[Any]:
        """Connects to every server and returns one MCPTool per remote tool.

        A server that fails to start is logged and left out. The others still run.
        """
        # Imported here to avoid a circular import: tools.mcp uses this module.
        from .tools.mcp import MCPTool

        self._thread.start()
        tools: list[MCPTool] = []
        for name, config in self.servers.items():
            try:
                remote_tools = self._start_server(name, config)
            except Exception as e:  # noqa: BLE001 - one broken server must not stop the others
                logger.warning("MCP server failed to start", server=name, error=str(e))
                continue
            tools.extend(MCPTool(self, name, tool) for tool in remote_tools)
        return tools

    def _start_server(self, name: str, config: MCPServerConfig) -> list[types.Tool]:
        ready: concurrent.futures.Future[list[types.Tool]] = concurrent.futures.Future()
        self._serving[name] = asyncio.run_coroutine_threadsafe(
            self._serve(name, config, ready), self._loop
        )
        return ready.result(timeout=self.connect_timeout)

    async def _serve(
        self,
        name: str,
        config: MCPServerConfig,
        ready: concurrent.futures.Future[list[types.Tool]],
    ) -> None:
        try:
            async with Client(
                _transport_for(config), read_timeout_seconds=self.call_timeout
            ) as client:
                listed = await client.list_tools()
                self._clients[name] = client
                ready.set_result(listed.tools)
                await self._stop.wait()
        except Exception as e:  # noqa: BLE001 - reported to the caller or logged, never raised
            if ready.done():
                logger.warning(
                    "MCP server stopped with an error", server=name, error=str(e)
                )
            else:
                ready.set_exception(e)
        finally:
            self._clients.pop(name, None)

    def call_tool(
        self, server: str, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult:
        """Runs a tool on a server and waits for its result."""
        client = self._clients.get(server)
        if client is None:
            raise MCPToolError(f"MCP server '{server}' is not connected.")
        future = asyncio.run_coroutine_threadsafe(
            client.call_tool(tool_name, arguments), self._loop
        )
        try:
            return future.result(timeout=self.call_timeout)
        except TimeoutError as e:
            future.cancel()
            raise MCPToolError(
                f"Tool '{tool_name}' on server '{server}' timed out after "
                f"{self.call_timeout} seconds."
            ) from e
        except Exception as e:
            raise MCPToolError(
                f"Tool '{tool_name}' on server '{server}' failed: {e}"
            ) from e

    def close(self) -> None:
        """Stops all servers and the event loop thread. Safe to call more than once."""
        if not self._thread.is_alive():
            return
        self._loop.call_soon_threadsafe(self._stop.set)
        for name, future in self._serving.items():
            try:
                future.result(timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except Exception:  # noqa: BLE001 - shutdown must finish for every server
                logger.warning("MCP server did not stop cleanly", server=name)
                future.cancel()
        self._serving.clear()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=SHUTDOWN_TIMEOUT_SECONDS)
        if not self._thread.is_alive():
            self._loop.close()
