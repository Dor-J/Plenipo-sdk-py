# Examples

Integration templates for connecting agents to Plenipo.

## Agent skills (MCP + Cursor)

| File | Purpose |
| --- | --- |
| [agent/SKILL.md](./agent/SKILL.md) | Cursor Agent Skill — when/how to use Plenipo MCP tools |
| [agent/mcp.json.example](./agent/mcp.json.example) | Cursor MCP config template (copy to `.cursor/mcp.json`) |
| [agent/mcp.local-lab.json.example](./agent/mcp.local-lab.json.example) | Local-lab stdio MCP config for a laptop-local Python agent |

### Quick start

1. Install the SDK and configure `.env` (see [README](../README.md)).
2. Copy `agent/mcp.json.example` → `.cursor/mcp.json` and set absolute paths + secrets.
3. Copy `agent/SKILL.md` → `.cursor/skills/plenipo/SKILL.md`.

Works with Claude Desktop, Codex, and any MCP host — use the same `command`/`args`/`env`
under your host's `mcpServers` key.

The local-lab MCP example is still stdio MCP. It is for an MCP host running on the same
laptop as the SDK process; it is not a remote HTTP MCP bridge.

On macOS/Linux, set `command` to `.venv/bin/python` instead of `.venv/Scripts/python.exe`.
