"""Reads MCP server definitions from `mcpServers` JSON files, the format used by Claude Code and Cursor."""

import json
from pathlib import Path

import structlog
from pydantic import BaseModel, Field, ValidationError, model_validator

logger = structlog.get_logger(__name__)

MCP_CONFIG_KEY = "mcpServers"


class InvalidMCPConfigError(ValueError):
    """Raised when an MCP config file is not a valid `mcpServers` document."""


class MCPServerConfig(BaseModel):
    """How to reach one MCP server: a local stdio command or a remote URL."""

    command: str | None = Field(
        None, description="Executable that starts a stdio server."
    )
    args: list[str] = Field(
        default_factory=list, description="Arguments for the command."
    )
    env: dict[str, str] | None = Field(
        None, description="Environment variables for the command."
    )
    url: str | None = Field(None, description="URL of a remote Streamable HTTP server.")

    @model_validator(mode="after")
    def _check_transport(self) -> MCPServerConfig:
        if (self.command is None) == (self.url is None):
            raise ValueError("Set exactly one of 'command' (stdio) or 'url' (HTTP).")
        return self

    def describe(self) -> str:
        """Returns a short, human-readable form of how the server is started."""
        if self.url is not None:
            return self.url
        return " ".join([self.command or "", *self.args])


def default_mcp_config_files() -> list[Path]:
    """Returns the MCP config files in priority order: project first, then user."""
    return [
        Path(".mcp.json"),
        Path(".cursor") / "mcp.json",
        Path.home() / ".config" / "agent" / "mcp.json",
    ]


def load_mcp_config(path: Path) -> dict[str, MCPServerConfig]:
    """Reads one config file. Invalid servers are skipped with a warning.

    Raises InvalidMCPConfigError if the file is not JSON or has no `mcpServers` object.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InvalidMCPConfigError(f"{path} is not valid JSON: {e}") from e

    entries = data.get(MCP_CONFIG_KEY) if isinstance(data, dict) else None
    if not isinstance(entries, dict):
        raise InvalidMCPConfigError(
            f"{path} must contain an '{MCP_CONFIG_KEY}' object."
        )

    servers: dict[str, MCPServerConfig] = {}
    for name, entry in entries.items():
        try:
            servers[name] = MCPServerConfig.model_validate(entry)
        except ValidationError as e:
            logger.warning(
                "Skipping invalid MCP server", path=str(path), server=name, error=str(e)
            )
    return servers


def discover_mcp_servers(paths: list[Path]) -> dict[str, MCPServerConfig]:
    """Merges the servers from each config file. Earlier files win on name clashes.

    Missing files are ignored. Unreadable or invalid files are skipped with a warning.
    """
    servers: dict[str, MCPServerConfig] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            loaded = load_mcp_config(path)
        except (OSError, InvalidMCPConfigError) as e:
            logger.warning("Skipping MCP config file", path=str(path), error=str(e))
            continue
        for name, config in loaded.items():
            if name in servers:
                logger.warning(
                    "Skipping duplicate MCP server", server=name, path=str(path)
                )
                continue
            servers[name] = config
    return dict(sorted(servers.items()))
