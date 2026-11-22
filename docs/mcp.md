# MCP servers

The agent can use tools from [Model Context Protocol](https://modelcontextprotocol.io) (MCP) servers. Each tool a server offers appears to the model like a built-in tool.

## Configuring servers

Servers are defined in a JSON file with an `mcpServers` object. This is the same format used by Claude Code and Cursor:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

A stdio server needs `command`, and may also set `args` and `env`. A remote server uses `url` instead. Each entry must set exactly one of `command` or `url`. Invalid entries are skipped and a warning is written to the log file.

## Where servers are loaded from

Config files are read in this order:

1. `<working dir>/.mcp.json` (the project).
2. `<working dir>/.cursor/mcp.json` (the project).
3. `~/.config/agent/mcp.json` (the user).

Servers from all files are merged. If two files define a server with the same name, the one from the earlier file wins.

To use one specific file instead, set `AGENT_MCP_CONFIG` in `.env` or the environment:

```
AGENT_MCP_CONFIG=/path/to/mcp.json
```

## Approval

Config files can come from any cloned repository, so the agent never starts a server on its own. At startup it lists each server it found, with the command or URL, and asks `Start this server?` for each one. The default answer is no. Only approved servers are started, and they are all stopped when the agent exits.

## Tool names and results

- Each remote tool is named `<server>__<tool>`, for example `chrome-devtools__navigate_page`. This avoids clashes with built-in tools.
- The tool's JSON schema comes from the server, and is shown to the model in the system prompt.
- Text results are returned to the model. Image results are saved to temporary files and attached to the next message.
- A tool that reports an error is shown to the model as an error.
- Each call times out after 120 seconds. A server that fails to start is skipped and the others keep working.

## Limitations

- Only stdio and Streamable HTTP servers are supported.
- Approval is asked once per server at startup. The agent does not check tool arguments before calling a tool.
- Servers that need OAuth or interactive input are not supported.
- Running `chrome-devtools-mcp` requires Node.js and `npx` on your machine.
