from typing import ClassVar

import pytest
from mcp import types

from agent import mcp_client
from agent.mcp_client import MCPConnectionManager, MCPToolError
from agent.mcp_config import MCPServerConfig


class FakeClient:
    """Stands in for mcp.Client. Tracks entry and exit so tests can check shutdown."""

    events: ClassVar[list[str]] = []
    tools: ClassVar[list[types.Tool]] = []
    fail_on_enter: ClassVar[bool] = False

    def __init__(self, transport, read_timeout_seconds=None):
        self.transport = transport
        self.read_timeout_seconds = read_timeout_seconds

    async def __aenter__(self):
        if FakeClient.fail_on_enter:
            raise RuntimeError("cannot start")
        FakeClient.events.append("enter")
        return self

    async def __aexit__(self, *exc):
        FakeClient.events.append("exit")

    async def list_tools(self):
        return types.ListToolsResult(tools=FakeClient.tools)

    async def call_tool(self, name, arguments):
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"{name}:{arguments}")]
        )


@pytest.fixture(autouse=True)
def fake_client(monkeypatch):
    FakeClient.events = []
    FakeClient.fail_on_enter = False
    FakeClient.tools = [
        types.Tool(name="ping", description="Pings.", input_schema={"type": "object"})
    ]
    monkeypatch.setattr(mcp_client, "Client", FakeClient)
    return FakeClient


def test_start_returns_namespaced_tools_and_call_tool_forwards(fake_client):
    manager = MCPConnectionManager({"docs": MCPServerConfig(command="python")})
    try:
        tools = manager.start()

        assert [tool.name for tool in tools] == ["docs__ping"]
        output = tools[0].execute()
        assert output.text == "ping:{}"
    finally:
        manager.close()


def test_close_shuts_down_the_client(fake_client):
    manager = MCPConnectionManager({"docs": MCPServerConfig(command="python")})
    manager.start()

    manager.close()

    assert FakeClient.events == ["enter", "exit"]


def test_failed_server_is_skipped_and_others_still_start(monkeypatch, fake_client):
    servers = {
        "broken": MCPServerConfig(command="missing"),
        "docs": MCPServerConfig(command="python"),
    }
    real_serve = MCPConnectionManager._serve

    async def serve(self, name, config, ready):
        if name == "broken":
            ready.set_exception(RuntimeError("no such command"))
            return
        await real_serve(self, name, config, ready)

    monkeypatch.setattr(MCPConnectionManager, "_serve", serve)
    manager = MCPConnectionManager(servers)
    try:
        tools = manager.start()

        assert [tool.name for tool in tools] == ["docs__ping"]
    finally:
        manager.close()


def test_call_to_unknown_server_raises(fake_client):
    manager = MCPConnectionManager({})
    manager.start()
    try:
        with pytest.raises(MCPToolError, match="not connected"):
            manager.call_tool("nope", "ping", {})
    finally:
        manager.close()
