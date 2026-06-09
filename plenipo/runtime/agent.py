"""Autonomous Agent Runtime v0."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from nacl.public import PrivateKey, SealedBox

from plenipo.client.relay import PlenipoClient, SendAck
from plenipo.crypto import base64url
from plenipo.did.resolve import resolve_enc_public_key
from plenipo.identity.provision import ensure_identity
from plenipo.identity.route import declare_route
from plenipo.identity.store import AgentIdentity
from plenipo.identity.sync import sync_identity_with_core
from plenipo.route_defaults import default_route_service_fields
from plenipo.runtime.events import (
    AgentEvent,
    ConnectEvent,
    DeliveryReceiptEvent,
    DisconnectEvent,
    ErrorEvent,
    MessageEvent,
)
from plenipo.runtime.state import load_runtime_state, save_runtime_state, update_receipt_cursor


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


@dataclass
class PlenipoAgentRuntime:
    """Long-lived autonomous agent runtime with reconnect and receipt recovery."""

    _identity: AgentIdentity | None = field(default=None, init=False)
    _client: PlenipoClient | None = field(default=None, init=False)
    _events: asyncio.Queue[AgentEvent] = field(default_factory=asyncio.Queue, init=False)
    _running: bool = field(default=False, init=False)
    _reconnect_task: asyncio.Task[None] | None = field(default=None, init=False)
    _seen_receipt_ids: set[str] = field(default_factory=set, init=False)
    _route_declared: bool = field(default=False, init=False)

    async def __aenter__(self) -> PlenipoAgentRuntime:
        await self.ensure_ready()
        self._running = True
        self._reconnect_task = asyncio.create_task(self._maintain_connection())
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self._running = False
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self._client is not None:
            await self._client.disconnect()

    async def ensure_ready(self) -> AgentIdentity:
        """Loads identity, syncs with Core, ensures route metadata, and connects."""
        identity = await ensure_identity()
        synced, _ = await sync_identity_with_core(identity)
        self._identity = synced

        if not self._route_declared and not _document_has_route(synced.document):
            defaults = default_route_service_fields()
            await declare_route(
                protocols=defaults['protocols'],
                capabilities=['general', 'mcp'],
                payment=defaults['payment'],
                limits=defaults['limits'],
            )
            self._route_declared = True

        await self._connect_client()
        return synced

    async def send(
        self,
        recipient_did: str,
        message: str,
        recipient_document_url: str | None = None,
    ) -> SendAck:
        """Sends an encrypted paid message and returns billing metadata."""
        client = await self._ensure_client()
        enc_key = await resolve_enc_public_key(
            recipient_did,
            recipient_document_url=recipient_document_url,
            registry_url=self._identity.registry_url if self._identity else None,
            relay_http_url=client.relay_http_url,
        )
        return await client.send(recipient_did, message, enc_key)

    async def list_receipts(
        self,
        *,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetches persisted delivery receipts for this sender."""
        client = await self._ensure_client()
        return await client.list_receipts(since=since, limit=limit)

    async def events(self) -> AsyncIterator[AgentEvent]:
        """Yields runtime events as they occur."""
        while True:
            yield await self._events.get()

    async def _ensure_client(self) -> PlenipoClient:
        if self._client is None or not self._client.connected:
            await self._connect_client()
        assert self._client is not None
        return self._client

    async def _connect_client(self) -> None:
        if self._identity is None:
            self._identity = await ensure_identity()

        if self._client is not None:
            await self._client.disconnect()

        client = PlenipoClient(
            did=self._identity.did,
            auth_secret_b64=self._identity.auth_secret_b64,
            did_document_url=self._identity.did_document_url,
            relay_url=self._identity.relay_url,
            auto_receipt=True,
        )
        enc_secret = self._identity.enc_secret_b64

        def on_message(envelope: dict[str, Any]) -> None:
            plaintext = None
            if enc_secret and envelope.get('ciphertext'):
                try:
                    key = PrivateKey(base64url.decode(enc_secret))
                    plain = SealedBox(key).decrypt(base64url.decode(envelope['ciphertext']))
                    plaintext = plain.decode('utf-8')
                except Exception:
                    pass
            self._events.put_nowait(
                MessageEvent(
                    envelope_id=str(envelope.get('envelope_id', '')),
                    sender_did=envelope.get('sender_did'),
                    recipient_did=envelope.get('recipient_did'),
                    plaintext=plaintext,
                    created_at=envelope.get('created_at'),
                )
            )

        def on_receipt(payload: dict[str, Any]) -> None:
            envelope_id = str(payload.get('envelope_id', ''))
            if not envelope_id or envelope_id in self._seen_receipt_ids:
                return
            self._seen_receipt_ids.add(envelope_id)
            event = self._receipt_event_from_payload(payload, recovered=False)
            self._events.put_nowait(event)
            if event.delivered_at:
                update_receipt_cursor(event.delivered_at)
            elif event.received_at:
                update_receipt_cursor(event.received_at)

        client.on_message(on_message)
        client.on_receipt(on_receipt)
        await client.connect()
        self._client = client
        await self._recover_missed_receipts()
        self._events.put_nowait(ConnectEvent(did=self._identity.did))

    async def _recover_missed_receipts(self) -> None:
        if self._client is None:
            return

        state = load_runtime_state()
        receipts = await self._client.list_receipts(
            since=state.last_receipt_seen_at,
            limit=100,
        )

        latest_cursor = state.last_receipt_seen_at
        for payload in receipts:
            envelope_id = str(payload.get('envelope_id', ''))
            if not envelope_id or envelope_id in self._seen_receipt_ids:
                continue
            self._seen_receipt_ids.add(envelope_id)
            event = self._receipt_event_from_payload(payload, recovered=True)
            self._events.put_nowait(event)
            latest_cursor = event.delivered_at or event.received_at or latest_cursor

        if latest_cursor and latest_cursor != state.last_receipt_seen_at:
            state.last_receipt_seen_at = latest_cursor
            save_runtime_state(state)

    async def _maintain_connection(self) -> None:
        backoff = 1.0
        while self._running:
            await asyncio.sleep(1.0)
            if self._client is None or not self._client.connected:
                self._events.put_nowait(DisconnectEvent(reason='relay disconnected'))
                try:
                    await self._connect_client()
                    backoff = 1.0
                except Exception as exc:
                    self._events.put_nowait(ErrorEvent(message=str(exc)))
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)

    async def disconnect(self) -> None:
        """Disconnects the relay client without stopping the runtime loop."""
        if self._client is not None:
            await self._client.disconnect()

    @staticmethod
    def _receipt_event_from_payload(
        payload: dict[str, Any],
        *,
        recovered: bool,
    ) -> DeliveryReceiptEvent:
        return DeliveryReceiptEvent(
            envelope_id=str(payload.get('envelope_id', '')),
            sender_did=payload.get('sender_did'),
            recipient_did=payload.get('recipient_did'),
            ciphertext_bytes=_optional_int(payload.get('ciphertext_bytes')),
            billable_kb=_optional_int(payload.get('billable_kb')),
            charged_tokens=_optional_int(payload.get('charged_tokens')),
            balance_after=_optional_int(payload.get('balance_after')),
            received_at=payload.get('received_at'),
            delivered_at=payload.get('delivered_at'),
            recovered=recovered,
        )


def _document_has_route(document: dict[str, Any]) -> bool:
    for service in document.get('service') or []:
        if service.get('type') == 'PlenipoAgent' and service.get('protocols'):
            return True
    return False
