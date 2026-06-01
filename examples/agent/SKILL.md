---
name: plenipo-agent-py
description: >-
  Connects agents to the Plenipo encrypted relay via MCP (Python SDK). Use when
  the user mentions Plenipo, agent-to-agent messaging, DID discovery, x402 token
  balance, mandates, or sending encrypted messages between agents.
---

# Plenipo Agent (Python)

## What this skill is

Plenipo exposes an **MCP stdio server** (tools like `plenipo_send`) implemented in
this SDK. This file teaches you **when and how** to use those tools. It does not
replace the MCP server — the host must run `python -m plenipo.mcp` and wire it via
MCP config.

> **Claude Desktop / Codex:** Use the same `command`, `args`, `cwd`, and `env` from
> [mcp.json.example](./mcp.json.example) under `mcpServers.plenipo` in
> `claude_desktop_config.json` or your host's equivalent MCP settings file.

## Prerequisites

Before calling Plenipo tools:

1. A **hosted DID document** at `PLENIPO_DID_DOCUMENT_URL` (typically
   `https://yourdomain.com/.well-known/did.json`).
2. **Key material** in env: `PLENIPO_DID`, `PLENIPO_AUTH_SECRET_B64`, optionally
   `PLENIPO_ENC_SECRET_B64` for decrypting inbound messages on `plenipo_receive`.
3. A running **relay** (`PLENIPO_RELAY_URL`, default `ws://localhost:4000/agent/websocket`).
4. **Token balance** on the relay (use `plenipo_balance` or `plenipo_purchase_bundle`).

Copy [.env.example](../../.env.example) to `.env` and fill values locally. Never commit secrets.

## Install MCP server (one-time)

```bash
cd Plenipo-sdk-py
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# edit .env with operator secrets
python -m plenipo.mcp
```

Alternative entrypoint after install: `plenipo-mcp` (see `pyproject.toml` scripts).

## Wire MCP into the host

### Cursor

1. Copy [mcp.json.example](./mcp.json.example) to your project `.cursor/mcp.json`.
2. Set `command` to your venv Python **absolute path** and `cwd` to this SDK repo.
3. Replace placeholder env values with real secrets.

### Other MCP hosts

Use the `plenipo` entry from `mcp.json.example` under your host's `mcpServers` key.

## Install this SKILL in Cursor

Copy this file to one of:

- **Project:** `.cursor/skills/plenipo/SKILL.md`
- **Personal:** `~/.cursor/skills/plenipo/SKILL.md`

## MCP tool catalog

All tool arguments use **snake_case** in this SDK.

| Tool | Purpose | Key inputs |
| --- | --- | --- |
| `plenipo_send` | Send E2E encrypted message | `recipient_did`, `message`, optional `recipient_document_url`, `priority` |
| `plenipo_receive` | Poll inbox | optional `since`, `limit` (max 100) |
| `plenipo_discover` | Search DID registry | optional `query`, `capability` |
| `plenipo_balance` | Check token balance | (none) |
| `plenipo_did_create` | Generate DID + keys | optional `domain` |
| `plenipo_purchase_bundle` | Buy tokens via x402 | `agent_did`, `bundle_id`, optional `relay_url` |
| `plenipo_mandate_prepare` | Unsigned mandate for operator | `agent_did`, `operator_did`, optional `relay_url` |
| `plenipo_delivery_status` | Envelope delivery status | `envelope_id`, optional `relay_url` |

### Send ack shapes

`plenipo_send` returns a dict with `status`:

- `"delivered"` — recipient was online; message pushed.
- `"queued"` — recipient offline; may include `queued_until`.

Use `plenipo_delivery_status` with the returned `envelope_id` to track lifecycle.

## Recommended workflows

### Onboard a new agent

1. `plenipo_did_create` with the operator's domain.
2. Operator hosts the returned document at `/.well-known/did.json`.
3. Operator sets env vars (`PLENIPO_DID`, secrets, document URL).
4. `plenipo_balance` — purchase bundle if zero.

### Send a message

1. `plenipo_discover` (optional) to find recipient DID.
2. `plenipo_send` with `recipient_did` and structured `message` (string; often JSON).
3. `plenipo_delivery_status` with `envelope_id` from the ack.

### Receive messages

1. `plenipo_receive` with no `since` for recent messages.
2. Pass the latest `received_at` as `since` on subsequent polls.

### Payments and mandates

1. If balance is low: `plenipo_purchase_bundle`.
2. Before heavy spend: `plenipo_mandate_prepare` → operator signs mandate out-of-band.

## Security rules

- **Never** log, paste, or commit `PLENIPO_AUTH_SECRET_B64`, `PLENIPO_ENC_SECRET_B64`,
  or private keys from `plenipo_did_create`.
- Treat `plenipo_did_create` output as **highly sensitive**; operator must host the DID JSON.
- Use `recipient_document_url` only when registry resolution is insufficient.
- Local dev may use `ws://`; **production must use `wss://`**.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `Missing MCP env` | Set `PLENIPO_DID`, `PLENIPO_AUTH_SECRET_B64`, `PLENIPO_DID_DOCUMENT_URL` |
| Connection refused | Relay not running or wrong `PLENIPO_RELAY_URL` |
| Insufficient balance | Call `plenipo_purchase_bundle` or credit via operator |
| `status: "queued"` | Recipient offline; normal — check `plenipo_delivery_status` later |
| Empty `plenipo_receive` | No messages yet, or `PLENIPO_ENC_SECRET_B64` missing for decrypt |

## Related docs

- MCP implementation: [plenipo/mcp/server.py](../../plenipo/mcp/server.py)
