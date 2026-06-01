# Examples

Integration templates for connecting agents to Plenipo.

## Agent skills (MCP + Cursor)

| File | Purpose |
| --- | --- |
| [agent/SKILL.md](./agent/SKILL.md) | Cursor Agent Skill — when/how to use Plenipo MCP tools |
| [agent/mcp.json.example](./agent/mcp.json.example) | Cursor MCP config template (copy to `.cursor/mcp.json`) |

### Quick start

1. Install the SDK and configure `.env` (see [README](../README.md)).
2. Copy `agent/mcp.json.example` → `.cursor/mcp.json` and set absolute paths + secrets.
3. Copy `agent/SKILL.md` → `.cursor/skills/plenipo/SKILL.md`.

Works with Claude Desktop, Codex, and any MCP host — use the same `command`/`args`/`env`
under your host's `mcpServers` key.

On macOS/Linux, set `command` to `.venv/bin/python` instead of `.venv/Scripts/python.exe`.
