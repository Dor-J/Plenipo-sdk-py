# Plenipo SDK (Python)

> MCP-native skill and client for LangChain, AutoGen, CrewAI, LlamaIndex, and custom Python agents.

**plenipo-mcp** connects Python 3.11+ agents to the Plenipo relay: DID authentication, E2E encrypted messaging, discovery, dev-token billing, and autonomous Agent Runtime v0 — exposed as an MCP server, a long-lived runtime CLI, and a library.

## Status

Active development. Core relay, Registry discovery, Route Records v1, MCP tools, and **Agent Runtime v0** are implemented for local autonomous messaging. Wallet x402 per-message payment, marketplace, task protocol, and production wallet funding are **not** implemented in this slice.

## Features

- **MCP server** — poll-based tools for send, receive, discover, balance, identity, route declaration, and receipt replay
- **Agent Runtime v0** — `PlenipoAgentRuntime` with auto-reconnect, decrypt-on-receive, and missed receipt recovery via `receipt.list`
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

## Agent Runtime v0

For autonomous agents that stay connected (not poll-based MCP), use the runtime:

```python
from plenipo.runtime import PlenipoAgentRuntime

async with PlenipoAgentRuntime() as agent:
    async for event in agent.events():
        print(event.type, event)
```

Or via CLI:

```bash
python -m plenipo.agent run --print-events
plenipo-agent run --capability mcp --protocol plenipo.message.v1 --print-events
```

Runtime behavior:

- Loads/creates identity from `~/.plenipo/identity.json`
- Syncs with Core and declares a default Route Record when missing
- Auto-reconnects with bounded exponential backoff
- Decrypts inbound messages (never persists plaintext by default)
- Recovers missed delivery receipts after reconnect using `receipt.list` and `runtime-state.json`

Use `--print-plaintext` only when you explicitly need decrypted message bodies in logs.

## Layout

```
plenipo/
├── agent/          # plenipo-agent CLI
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
```

Requires **Python 3.11+**.

### E2E scripts (with Core + Registry running)

```bash
python scripts/test-two-agent-messaging.py
python scripts/test-two-agent-messaging.py --use-runtime
python scripts/test-agent-runtime-reconnect.py
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
