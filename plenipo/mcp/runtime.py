"""Shared MCP runtime with connected relay client and message buffer."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from nacl.public import PrivateKey, SealedBox

from plenipo.client.relay import PlenipoClient, SendAck
from plenipo.crypto import base64url
from plenipo.did.resolve import resolve_enc_public_key


@dataclass(frozen=True)
class McpRuntimeConfig:
    """Configuration for MCP relay tools."""

    did: str
    auth_secret_b64: str
    did_document_url: str
    relay_url: str
    enc_secret_b64: str | None = None
    registry_url: str | None = None


@dataclass
class BufferedMessage:
    """Buffered deliver or receipt event."""

    kind: Literal['deliver', 'receipt']
    envelope_id: str
    received_at_iso: str
    sender_did: str | None = None
    recipient_did: str | None = None
    created_at: str | None = None
    ciphertext: str | None = None
    plaintext: str | None = None
    receipt_received_at: str | None = None
    ciphertext_bytes: int | None = None
    billable_kb: int | None = None
    charged_tokens: int | None = None
    balance_after: int | None = None
    delivered_at: str | None = None


def load_mcp_config_from_env() -> McpRuntimeConfig:
    """Loads MCP agent configuration from environment variables."""
    from plenipo.identity.provision import identity_to_mcp_config
    from plenipo.identity.store import load_identity

    did = os.environ.get('PLENIPO_DID')
    auth = os.environ.get('PLENIPO_AUTH_SECRET_B64') or os.environ.get('PLENIPO_DID_PRIVATE_KEY')
    doc_url = os.environ.get('PLENIPO_DID_DOCUMENT_URL')
    relay = os.environ.get('PLENIPO_RELAY_URL', 'ws://localhost:4000/agent/websocket')

    if did and auth and doc_url:
        return McpRuntimeConfig(
            did=did,
            auth_secret_b64=auth,
            did_document_url=doc_url,
            relay_url=relay,
            enc_secret_b64=os.environ.get('PLENIPO_ENC_SECRET_B64'),
            registry_url=os.environ.get('PLENIPO_REGISTRY_URL'),
        )

    stored = load_identity()
    if stored is not None:
        return identity_to_mcp_config(stored)

    raise RuntimeError(
        'Missing MCP identity: set PLENIPO_DID, PLENIPO_AUTH_SECRET_B64, '
        'PLENIPO_DID_DOCUMENT_URL or run ensure_identity() before connecting'
    )


async def load_mcp_config() -> McpRuntimeConfig:
    """Loads MCP config from env, identity.json, or auto-provision."""
    from plenipo.identity.provision import ensure_identity, identity_to_mcp_config

    identity = await ensure_identity()
    return identity_to_mcp_config(identity)


@dataclass
class McpRuntime:
    """Connected client and in-memory message buffer for MCP tools."""

    config: McpRuntimeConfig
    _client: PlenipoClient | None = field(default=None, init=False)
    _connected: bool = field(default=False, init=False)
    _buffer: list[BufferedMessage] = field(default_factory=list, init=False)

    async def ensure_connected(self) -> PlenipoClient:
        """Connects the relay client once and registers buffer handlers."""
        if self._client is None:
            client = PlenipoClient(
                did=self.config.did,
                auth_secret_b64=self.config.auth_secret_b64,
                did_document_url=self.config.did_document_url,
                relay_url=self.config.relay_url,
                auto_receipt=True,
            )
            enc_secret = self.config.enc_secret_b64

            def on_message(envelope: dict[str, Any]) -> None:
                entry = BufferedMessage(
                    kind='deliver',
                    envelope_id=str(envelope.get('envelope_id', '')),
                    sender_did=envelope.get('sender_did'),
                    recipient_did=envelope.get('recipient_did'),
                    created_at=envelope.get('created_at'),
                    ciphertext=envelope.get('ciphertext'),
                    received_at_iso=datetime.now(timezone.utc).isoformat(),
                )
                if enc_secret and envelope.get('ciphertext'):
                    try:
                        key = PrivateKey(base64url.decode(enc_secret))
                        plain = SealedBox(key).decrypt(base64url.decode(envelope['ciphertext']))
                        entry.plaintext = plain.decode('utf-8')
                    except Exception:
                        pass
                self._buffer.append(entry)

            def on_receipt(payload: dict[str, Any]) -> None:
                self._buffer.append(
                    BufferedMessage(
                        kind='receipt',
                        envelope_id=str(payload.get('envelope_id', '')),
                        sender_did=payload.get('sender_did'),
                        recipient_did=payload.get('recipient_did'),
                        receipt_received_at=payload.get('received_at'),
                        received_at_iso=datetime.now(timezone.utc).isoformat(),
                        ciphertext_bytes=_optional_int(payload.get('ciphertext_bytes')),
                        billable_kb=_optional_int(payload.get('billable_kb')),
                        charged_tokens=_optional_int(payload.get('charged_tokens')),
                        balance_after=_optional_int(payload.get('balance_after')),
                        delivered_at=payload.get('delivered_at'),
                    )
                )

            client.on_message(on_message)
            client.on_receipt(on_receipt)
            self._client = client

        if not self._connected:
            await self._client.connect()
            self._connected = True

        return self._client

    async def send(
        self,
        recipient_did: str,
        message: str,
        recipient_document_url: str | None = None,
    ) -> SendAck:
        """Sends an encrypted message to another agent."""
        client = await self.ensure_connected()
        enc_key = await resolve_enc_public_key(
            recipient_did,
            recipient_document_url=recipient_document_url,
            registry_url=self.config.registry_url,
            relay_http_url=client.relay_http_url,
        )
        return await client.send(recipient_did, message, enc_key)

    async def get_balance(self) -> int:
        """Returns current token balance."""
        client = await self.ensure_connected()
        return await client.get_balance()

    async def list_receipts(
        self,
        *,
        since: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetches persisted delivery receipts for this sender."""
        client = await self.ensure_connected()
        result = await client.list_receipts(since=since, cursor=cursor, limit=limit)
        receipts = result.get('receipts', [])
        if not isinstance(receipts, list):
            return []
        return receipts

    def drain_messages(self, since: str | None = None, limit: int = 100) -> list[BufferedMessage]:
        """Returns and removes buffered messages matching optional since cursor."""
        drained: list[BufferedMessage] = []
        kept: list[BufferedMessage] = []

        for entry in self._buffer:
            eligible = (
                not since
                or entry.received_at_iso > since
                or entry.envelope_id > since
                or (entry.created_at is not None and entry.created_at > since)
            )
            if eligible and len(drained) < limit:
                drained.append(entry)
            else:
                kept.append(entry)

        self._buffer = kept
        return drained


_default_runtime: McpRuntime | None = None


def get_mcp_runtime() -> McpRuntime:
    """Returns the process-wide MCP runtime."""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = McpRuntime(load_mcp_config_from_env())
    return _default_runtime


def set_mcp_runtime(runtime: McpRuntime) -> None:
    """Sets the process-wide MCP runtime."""
    global _default_runtime
    _default_runtime = runtime


def reset_mcp_runtime() -> None:
    """Resets runtime singleton (for tests)."""
    global _default_runtime
    _default_runtime = None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
