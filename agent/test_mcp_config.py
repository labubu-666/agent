import json
from pathlib import Path

import pytest

from agent.mcp_config import (
    InvalidMCPConfigError,
    MCPServerConfig,
    discover_mcp_servers,
    load_mcp_config,
)

CHROME_CONFIG = {
    "mcpServers": {
        "chrome-devtools": {
            "command": "npx",
            "args": ["-y", "chrome-devtools-mcp@latest"],
        }
    }
}


def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_mcp_config_reads_stdio_server(tmp_path):
    path = _write_json(tmp_path / ".mcp.json", CHROME_CONFIG)

    servers = load_mcp_config(path)

    assert servers == {
        "chrome-devtools": MCPServerConfig(
            command="npx", args=["-y", "chrome-devtools-mcp@latest"]
        )
    }


def test_load_mcp_config_reads_http_server(tmp_path):
    path = _write_json(
        tmp_path / ".mcp.json",
        {"mcpServers": {"docs": {"url": "https://example.com/mcp"}}},
    )

    assert load_mcp_config(path)["docs"].url == "https://example.com/mcp"


def test_load_mcp_config_skips_invalid_servers(tmp_path):
    path = _write_json(
        tmp_path / ".mcp.json",
        {
            "mcpServers": {
                "both": {"command": "x", "url": "https://example.com"},
                "neither": {},
                "good": {"command": "node"},
            }
        },
    )

    assert list(load_mcp_config(path)) == ["good"]


def test_load_mcp_config_rejects_missing_mcp_servers_key(tmp_path):
    path = _write_json(tmp_path / ".mcp.json", {"servers": {}})

    with pytest.raises(InvalidMCPConfigError, match="mcpServers"):
        load_mcp_config(path)


def test_load_mcp_config_rejects_invalid_json(tmp_path):
    path = tmp_path / ".mcp.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(InvalidMCPConfigError, match="not valid JSON"):
        load_mcp_config(path)


def test_discover_mcp_servers_earlier_files_win(tmp_path):
    project = _write_json(
        tmp_path / ".mcp.json",
        {"mcpServers": {"shared": {"command": "project-cmd"}}},
    )
    user = _write_json(
        tmp_path / "user.json",
        {
            "mcpServers": {
                "shared": {"command": "user-cmd"},
                "only-user": {"command": "other"},
            }
        },
    )

    servers = discover_mcp_servers([project, user])

    assert list(servers) == ["only-user", "shared"]
    assert servers["shared"].command == "project-cmd"


def test_discover_mcp_servers_ignores_missing_and_broken_files(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("nope", encoding="utf-8")
    good = _write_json(tmp_path / "good.json", CHROME_CONFIG)

    servers = discover_mcp_servers([tmp_path / "missing.json", broken, good])

    assert list(servers) == ["chrome-devtools"]


def test_default_mcp_config_files_checks_project_before_user(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    from agent.mcp_config import default_mcp_config_files

    assert default_mcp_config_files() == [
        Path(".mcp.json"),
        Path(".cursor") / "mcp.json",
        tmp_path / ".config" / "agent" / "mcp.json",
    ]


def test_describe_shows_command_or_url():
    stdio = MCPServerConfig(command="npx", args=["-y", "pkg"])
    http = MCPServerConfig(url="https://example.com/mcp")

    assert stdio.describe() == "npx -y pkg"
    assert http.describe() == "https://example.com/mcp"
