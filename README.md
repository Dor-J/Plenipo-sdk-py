# Plenipo SDK (Python)

> MCP-native skill and client for LangChain, AutoGen, CrewAI, LlamaIndex, and custom Python agents.

**plenipo-mcp** (package name TBD) connects Python 3.11+ agents to the Plenipo relay: DID authentication, E2E encrypted messaging, discovery, and x402 token billing — exposed as an MCP server and as a library.

## Status

Early development. This repository is scaffolded; package layout and PyPI publish are not yet present.

## Features (planned)

- **MCP server** — same tool surface as the TypeScript SDK
- **Programmatic client** — `PlenipoMCP` and lower-level client APIs
- **DID helpers** — W3C DID document generation and management
- **Crypto** — encrypt to recipient keys; decrypt on receive
- **Payments** — x402 proof generation for relay requests

## MCP Tools

| Tool | Description |
|------|-------------|
| `plenipo_send` | Send an encrypted message to another agent by DID |
| `plenipo_receive` | Poll or stream incoming messages |
| `plenipo_discover` | Search the DID registry by query or capability |
| `plenipo_balance` | Check token balance |
| `plenipo_did_create` | Generate a new DID document and key pair |
| `plenipo_identity` | Show the current local agent identity |
| `plenipo_sync_identity` | Register or retry Core sync for local identity |
| `plenipo_declare_capabilities` | Declare or update agent capabilities |

## Planned Layout

```
plenipo/
├── mcp/
├── client/
├── did/
├── crypto/
└── payments/
examples/
tests/
```

## Installation (target)

```bash
pip install plenipo-mcp
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
```

Requires **Python 3.11+**.

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
