import base64

import pytest
from mcp import types

from agent.mcp_client import MCPToolError
from agent.tools.mcp import MCPTool


class FakeManager:
    """Stands in for MCPConnectionManager and returns a canned result."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls: list[tuple[str, str, dict]] = []

    def call_tool(self, server, tool_name, arguments):
        self.calls.append((server, tool_name, arguments))
        if self.error is not None:
            raise self.error
        return self.result


def _remote_tool(name="search", description="Searches things."):
    return types.Tool(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


def test_tool_name_is_namespaced_by_server():
    tool = MCPTool(FakeManager(), "chrome-devtools", _remote_tool())

    assert tool.name == "chrome-devtools__search"
    assert tool.description == "Searches things."


def test_tool_uses_server_schema_for_prompt():
    tool = MCPTool(FakeManager(), "docs", _remote_tool())

    assert tool.json_schema()["required"] == ["query"]


def test_execute_forwards_arguments_and_joins_text_blocks():
    manager = FakeManager(
        result=types.CallToolResult(
            content=[
                types.TextContent(type="text", text="first"),
                types.TextContent(type="text", text="second"),
            ]
        )
    )
    tool = MCPTool(manager, "docs", _remote_tool())

    output = tool.execute(query="cats")

    assert manager.calls == [("docs", "search", {"query": "cats"})]
    assert output.text == "first\nsecond"
    assert output.image_paths == []


def test_execute_saves_image_blocks_to_files():
    png = base64.b64encode(b"\x89PNG fake").decode()
    manager = FakeManager(
        result=types.CallToolResult(
            content=[types.ImageContent(type="image", data=png, mime_type="image/png")]
        )
    )
    tool = MCPTool(manager, "docs", _remote_tool())

    output = tool.execute(query="cats")

    assert len(output.image_paths) == 1
    saved = output.image_paths[0]
    assert saved.endswith(".png")
    with open(saved, "rb") as file:
        assert file.read() == b"\x89PNG fake"


def test_execute_raises_on_server_errors():
    manager = FakeManager(
        result=types.CallToolResult(
            content=[types.TextContent(type="text", text="bad query")],
            is_error=True,
        )
    )
    tool = MCPTool(manager, "docs", _remote_tool())

    with pytest.raises(MCPToolError, match="reported an error: bad query"):
        tool.execute(query="cats")


def test_execute_propagates_manager_errors():
    manager = FakeManager(error=MCPToolError("server 'docs' is not connected."))
    tool = MCPTool(manager, "docs", _remote_tool())

    with pytest.raises(MCPToolError, match="not connected"):
        tool.execute(query="cats")
