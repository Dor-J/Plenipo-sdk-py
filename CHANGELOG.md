# Changelog

All notable changes to `plenipo-mcp` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [COMPATIBILITY.md](../COMPATIBILITY.md).

## [0.1.0-alpha] - 2026-06-14

### Added

- `llms.txt` agent-readable SDK summary at repo root.
- `plenipo ping` CLI for relay connectivity self-test against `did:web:echo.plenipo.dev`.
- Structured error helpers with `code`, `message`, and `docs_url` on SDK HTTP failures.
- MCP tools: send, receive, discover, balance, receipts, identity, route declaration.
- Agent Runtime v0.1 with durable outbox, receipt replay, and reconnect.
- Agent Sidecar v0.3.x with encrypted inbox, durable events, and SSE.
- CLI: `plenipo-agent`, `plenipo-mcp`.

### Experimental

- PyPI publish pipeline (alpha packaging in progress).
- x402 wallet payment rails (not in SDK stable surface).

### Compatibility

- Relay envelope `v: "1.0"`, `plenipo.message.v1`, Route Record v1, sidecar `0.3.x`.
- Public error codes documented at https://plenipo.dev/errors
