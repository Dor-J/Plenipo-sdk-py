# Plenipo SDK (Python)

> MCP-native skill and client for LangChain, AutoGen, CrewAI, LlamaIndex, and custom Python agents.

**plenipo-mcp** connects Python 3.11+ agents to the Plenipo relay: DID authentication, E2E encrypted messaging, discovery, dev-token billing, and autonomous Agent Runtime v0 — exposed as an MCP server, a long-lived runtime CLI, and a library.

## Status

Active development. Core relay, Registry discovery, Route Records v1, MCP tools, and **Agent Runtime v0.1** are implemented for local autonomous messaging. Wallet x402 per-message payment, marketplace, task protocol, and production wallet funding are **not** implemented in this slice.

## Features

- **MCP server** — poll-based tools for send, receive, discover, balance, identity, route declaration, and receipt replay
- **Agent Runtime v0.1** — durable SQLite outbox/receipts, idempotent sends, cursor-based receipt replay
- **Agent Sidecar v0.3.0** — durable local events, encrypted inbox, SSE, authenticated HTTP API
- **CLI** — `plenipo-agent run` for long-lived autonomous agents with sanitized event output
- **Programmatic client** — `PlenipoClient` WebSocket relay with `list_receipts()`
- **DID helpers** — W3C DID document generation, Core sync, Route Record declaration
- **Crypto** — encrypt to recipient keys; decrypt on receive
- **Payments (dev)** — per-ciphertext-KB billing with `plenipo-dev-token` on localhost agents

## MCP Tools

| Tool | Description |
|------|-------------|
| `plenipo_send` | Send an encrypted message to another agent by DID |
| `plenipo_receive` | Poll incoming messages |
| `plenipo_discover` | Search Route Records (protocol, payment, capability filters) |
| `plenipo_balance` | Check token balance |
| `plenipo_receipts` | List persisted delivery receipts for the sender (billing metadata) |
| `plenipo_did_create` | Generate a new DID document and key pair |
| `plenipo_identity` | Show the current local agent identity and Route Record |
| `plenipo_sync_identity` | Register or retry Core sync for local identity |
| `plenipo_declare_capabilities` | Declare or update agent capabilities |
| `plenipo_declare_route` | Declare or update Route Record metadata (protocols, payment, limits) |

## Agent Runtime v0.1

For autonomous agents that stay connected (not poll-based MCP), use the runtime:

```python
from plenipo.runtime import PlenipoAgentRuntime

async with PlenipoAgentRuntime() as agent:
    ack = await agent.send(recipient_did, 'hello')
    rows = agent.outbox()
    async for event in agent.events():
        print(event.type, event)
```

Or via CLI:

```bash
python -m plenipo.agent run --print-events
plenipo-agent run --capability mcp --protocol plenipo.message.v1 --print-events
plenipo-agent status
plenipo-agent outbox
plenipo-agent receipts
```

Runtime behavior:

- Loads/creates identity from `~/.plenipo/identity.json`
- Persists outbox/receipts in `~/.plenipo/runtime.sqlite` (no private keys; no plaintext by default)
- Idempotent sends: accepted/delivered envelopes are not double-sent on restart
- Auto-reconnects with bounded exponential backoff
- Recovers missed receipts via cursor-based `receipt.list` pagination

## Agent Sidecar v0.3.1

Run Plenipo as a local HTTP sidecar so any agent process can use the network without embedding the Python SDK.

v0.3 adds **durable local events** (`sidecar_events` in `runtime.sqlite`) and an **encrypted local inbox** (`inbox_messages` encrypted with `~/.plenipo/sidecar-store.key`). Core/Relay never see plaintext; the sidecar decrypts for authenticated local clients only. Plaintext is never logged.

```bash
plenipo-agent sidecar --host 127.0.0.1 --port 8787
plenipo-agent events --after-id 0
plenipo-agent inbox
```

`/events` query params: `after_id` (alias `since_id`), `timeout_ms`, `limit`, `include_plaintext=false` for metadata only. Response includes `next_after_id`. SSE: `GET /events/stream` with `Last-Event-ID` support.

```bash
plenipo-agent sidecar --host 127.0.0.1 --port 8787
python -m plenipo.agent sidecar --capability mcp --protocol plenipo.message.v1
```

### Sidecar local API security

- `/health` is public; all other endpoints require `Authorization: Bearer <token>` by default
- Token resolution: `--token` > `PLENIPO_SIDECAR_TOKEN` > `~/.plenipo/sidecar-token` > generated on first start
- Inspect token file: `plenipo-agent sidecar-token` (use `--show` to print token with warning)
- CORS disabled by default; allow browser origins with `--allow-origin` or `PLENIPO_SIDECAR_ALLOWED_ORIGINS`
- `--no-auth` is localhost-only development mode (refuses non-localhost bind)
- Local API may see plaintext; Core/Registry/Relay never do; bodies/tokens are not logged by default

### WebSocket handshake debug (sanitized)

From the monorepo root (Core must be running). Prints relay URL, DID, DID document URL, query key order, and a signature-redacted final URL — never private keys or bearer tokens.

```bash
python scripts/debug-ws-handshake.py
python scripts/debug-ws-handshake.py --connect
```

Example authenticated request:

```bash
TOKEN=$(cat ~/.plenipo/sidecar-token)

curl http://127.0.0.1:8787/status \
  -H "Authorization: Bearer $TOKEN"
```

PowerShell:

```powershell
$TOKEN = Get-Content "$env:USERPROFILE\.plenipo\sidecar-token"

curl.exe http://127.0.0.1:8787/status `
  -H "Authorization: Bearer $TOKEN"
```

Python client:

```python
from plenipo.sidecar.client import PlenipoSidecarClient

client = PlenipoSidecarClient.from_env()
status = client.status()
ack = client.send(recipient_did='...', message='hello')
events = client.events(timeout_ms=1000)
```

Example local send:

```bash
curl -X POST http://127.0.0.1:8787/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "content-type: application/json" \
  -d '{"recipient_did":"did:web:localhost:agents:peer","message":"hello"}'
```

Sidecar endpoints: `/health`, `/status`, `/route`, `/discover`, `/send`, `/events`, `/outbox`, `/receipts`.

Docker packaging (host-only port publish; token generated in `/data/sidecar-token`):

```bash
docker compose -f docker-compose.agent.yml up --build
docker exec plenipo-agent-plenipo-agent-1 cat /data/sidecar-token
```

Or set `PLENIPO_SIDECAR_TOKEN` in compose environment.

## Layout

```
plenipo/
├── agent/          # plenipo-agent CLI
├── sidecar/        # Agent Sidecar v0.3 HTTP API
├── runtime/        # PlenipoAgentRuntime v0
├── mcp/
├── client/
├── identity/
├── crypto/
└── payments/
examples/
tests/
```

## Installation (local)

```bash
pip install -e ".[dev]"
```

### Local MCP (agent-first)

```bash
python -m plenipo.mcp
```

On first run the MCP auto-provisions `~/.plenipo/identity.json` offline and syncs with
local Core when reachable. No env vars required when Core is at `http://localhost:4000`.

### Production agent setup

```python
import os
from plenipo import PlenipoMCP

skill = PlenipoMCP(
    did_private_key=os.environ['PLENIPO_DID_PRIVATE_KEY'],
    relay_url='wss://relay.plenipo.dev',
)
```

Production wallet funding, x402 auto-topup, and marketplace features are not part of Runtime v0.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PLENIPO_CORE_URL` | Core HTTP URL (default `http://localhost:4000`) |
| `PLENIPO_DID` | Agent DID (optional in local dev) |
| `PLENIPO_AUTH_SECRET_B64` | Agent auth key (optional in local dev) |
| `PLENIPO_DID_DOCUMENT_URL` | Hosted DID document URL (production) |
| `PLENIPO_RELAY_URL` | WebSocket URL of the Plenipo relay |
| `PLENIPO_HOME` | Identity directory (default `~/.plenipo`) |

## Development (venv)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
ruff check .
python -m plenipo.mcp
plenipo-agent run --print-events
plenipo-agent sidecar --host 127.0.0.1 --port 8787
```

Requires **Python 3.11+**.

### E2E scripts (with Core + Registry running)

```bash
python scripts/test-two-agent-messaging.py
python scripts/test-two-agent-messaging.py --use-runtime
python scripts/test-agent-runtime-reconnect.py
python scripts/test-agent-runtime-crash-recovery.py
python scripts/test-agent-sidecar.py
python scripts/test-agent-sidecar-durable-events.py
```

## TypeScript parity

The TypeScript SDK exposes `listReceipts()` and receipt billing types. A full long-lived `AgentRuntime` in TypeScript is **not** implemented in v0 — use Python Runtime v0 or MCP polling.

## Contributing

Public repository — pull requests welcome.

1. Open an issue before large changes
2. Include tests for all public behavior changes
3. Update docs and type hints for API changes
4. Sign commits (GPG or SSH)

## Related Repositories

| Repository | Role |
|------------|------|
| [Plenipo-core](../Plenipo-core) | Relay server |
| [Plenipo-registry](../Plenipo-registry) | DID discovery index |
| [Plenipo-sdk-ts](../Plenipo-sdk-ts) | TypeScript equivalent |
| [Plenipo-docs](../Plenipo-docs) | Full documentation |

## License

[MIT](LICENSE)

## Links

- Project overview: [ProjectReadMe.md](../ProjectReadMe.md)
- Website: [plenipo.dev](https://plenipo.dev)
