"""A tool backed by a tool hosted on an MCP server."""

import base64
import mimetypes
import tempfile
from typing import Any, Protocol

from mcp import types
from pydantic import BaseModel, ConfigDict

from ..mcp_client import MCPToolError
from .base import Tool, ToolOutput


class MCPCaller(Protocol):
    """Anything that can run a tool on a named MCP server, e.g. MCPConnectionManager."""

    def call_tool(
        self, server: str, tool_name: str, arguments: dict[str, Any]
    ) -> types.CallToolResult: ...


class MCPArgs(BaseModel):
    """Accepts any arguments. The server's own JSON schema is shown to the model instead."""

    model_config = ConfigDict(extra="allow")


class MCPTool(Tool):
    """Wraps one tool from an MCP server. Its name is '<server>__<tool>' to avoid clashes."""

    args_schema = MCPArgs

    def __init__(self, manager: MCPCaller, server_name: str, tool: types.Tool):
        self._manager = manager
        self._server_name = server_name
        self._remote_name = tool.name
        self._input_schema: dict[str, Any] = tool.input_schema
        self.name = f"{server_name}__{tool.name}"
        self.description = (
            tool.description or f"Tool '{tool.name}' from MCP server '{server_name}'."
        )

    def json_schema(self) -> dict[str, Any]:
        return self._input_schema

    def execute(self, **kwargs: Any) -> ToolOutput:
        result = self._manager.call_tool(self._server_name, self._remote_name, kwargs)
        text_parts: list[str] = []
        image_paths: list[str] = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                text_parts.append(block.text)
            elif isinstance(block, types.ImageContent):
                image_paths.append(_save_image(block))
            else:
                text_parts.append(
                    block.model_dump_json(by_alias=True, exclude_none=True)
                )
        text = "\n".join(text_parts) or "(no output)"
        if result.is_error:
            # Raised so the agent reports a failed tool run instead of a success.
            raise MCPToolError(f"The MCP tool reported an error: {text}")
        return ToolOutput(text=text, image_paths=image_paths)


def _save_image(block: types.ImageContent) -> str:
    """Writes base64 image data to a temporary file and returns its path."""
    data = base64.b64decode(block.data, validate=True)
    suffix = mimetypes.guess_extension(block.mime_type) or ".img"
    with tempfile.NamedTemporaryFile(
        delete=False, prefix="agent-mcp-", suffix=suffix
    ) as file:
        file.write(data)
    return file.name
