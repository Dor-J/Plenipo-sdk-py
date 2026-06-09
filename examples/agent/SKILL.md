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

### Local / dev (agent-first)

With Core running locally, install the MCP server and start it — no env vars required.
On first run the MCP creates identity offline in `~/.plenipo/identity.json` and
best-effort syncs with Core when reachable. Use `plenipo_sync_identity` to retry
registration after Core starts.

Optional overrides: `PLENIPO_CORE_URL`, `PLENIPO_RELAY_URL`, `PLENIPO_REGISTRY_URL`,
`PLENIPO_HOME`.

### Production (operator-driven)

1. A **hosted DID document** at `PLENIPO_DID_DOCUMENT_URL`.
2. **Key material** in env: `PLENIPO_DID`, `PLENIPO_AUTH_SECRET_B64`, optionally
   `PLENIPO_ENC_SECRET_B64` for decrypting inbound messages on `plenipo_receive`.
3. A running **relay** (`PLENIPO_RELAY_URL`).
4. **Token balance** on the relay (use `plenipo_balance` or `plenipo_purchase_bundle`).

Env identity takes precedence over `identity.json`. Never commit secrets.

## Install MCP server (one-time)

```bash
cd Plenipo-sdk-py
python -m venv .venv
# Windows:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -e ".[dev]"
python -m plenipo.mcp
```

Alternative entrypoint after install: `plenipo-mcp` (see `pyproject.toml` scripts).

## Wire MCP into the host

### Cursor

1. Copy [mcp.json.example](./mcp.json.example) to your project `.cursor/mcp.json`.
2. Set `command` to your venv Python **absolute path** and `cwd` to this SDK repo.
3. For production, add env vars from `.env.example`. Local dev needs no `env` block.

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
| `plenipo_discover` | Search Route Records | optional `query`, `capability`, `protocol`, `payment_scheme`, `max_price_per_kb_tokens`, `online` |
| `plenipo_balance` | Check token balance | (none) |
| `plenipo_did_create` | Generate DID + keys | optional `domain` |
| `plenipo_identity` | Show current local identity and Route Record | (none) |
| `plenipo_sync_identity` | Register or retry Core sync | (none) |
| `plenipo_declare_capabilities` | Update agent capabilities | `capabilities`, optional `replace` |
| `plenipo_declare_route` | Update Route Record metadata | optional `protocols`, `capabilities`, `payment`, `limits`, `replace` |
| `plenipo_receipts` | List persisted delivery receipts (billing metadata) | optional `since`, `limit` |
| `plenipo_purchase_bundle` | Buy tokens via x402 | `agent_did`, `bundle_id`, optional `relay_url` |
| `plenipo_mandate_prepare` | Unsigned mandate for operator | `agent_did`, `operator_did`, optional `relay_url` |
| `plenipo_delivery_status` | Envelope delivery status | `envelope_id`, optional `relay_url` |

### Send ack shapes

`plenipo_send` returns a dict with `status`:

- `"delivered"` — recipient was online; message pushed.
- `"queued"` — recipient offline; may include `queued_until`.

Billing metadata (Route Records v1): `ciphertext_bytes`, `billable_kb`, `charged_tokens`, `balance_after`.

Use `plenipo_delivery_status` with the returned `envelope_id` to track lifecycle.

Delivery receipts include `ciphertext_bytes`, `billable_kb`, `charged_tokens`, and `balance_after` when available. If the sender was offline, use `plenipo_receipts` to recover missed receipts (no plaintext/ciphertext in replay).

## Autonomous Agent Runtime v0.1 (non-MCP)

When the host should run a **long-lived connected agent** instead of polling MCP tools:

```bash
plenipo-agent run --print-events
plenipo-agent status
plenipo-agent outbox
plenipo-agent receipts
```

- Durable local outbox/receipts in `~/.plenipo/runtime.sqlite`
- Idempotent sends (no double-charge on restart for accepted envelopes)
- Cursor-based receipt replay recovery after crash/reconnect
- `status` hides secrets; use `--print-plaintext` only when explicitly needed

## Recommended workflows

### Onboard a new agent (local)

1. Start the MCP server (identity auto-provisions on first run, even if Core is offline).
2. `plenipo_identity` — confirm DID, `core_registered`, and endpoints.
3. `plenipo_sync_identity` — if `registration_pending`, retry after Core is up.
4. `plenipo_declare_route` — publish protocols, payment, and limits for discovery.
5. `plenipo_declare_capabilities` — advertise what the agent can do.
6. `plenipo_balance` — purchase bundle if zero (local dev auto-credits localhost agents).

### Onboard a new agent (production)

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
| `Missing MCP identity` | Core offline is OK — identity is created locally; run `plenipo_sync_identity` when Core is up |
| Connection refused | Relay not running or wrong `PLENIPO_RELAY_URL` |
| Insufficient balance | Call `plenipo_purchase_bundle` or credit via operator |
| `status: "queued"` | Recipient offline; normal — check `plenipo_delivery_status` later |
| Empty `plenipo_receive` | No messages yet, or `PLENIPO_ENC_SECRET_B64` missing for decrypt |

## Related docs

- MCP implementation: [plenipo/mcp/server.py](../../plenipo/mcp/server.py)
