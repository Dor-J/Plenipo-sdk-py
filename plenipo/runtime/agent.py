"""Autonomous Agent Runtime v0.1."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from nacl.public import PrivateKey, SealedBox

from plenipo.client.relay import PlenipoClient, SendAck, _generate_ulid
from plenipo.crypto import base64url
from plenipo.did.resolve import resolve_enc_public_key
from plenipo.identity.provision import ensure_identity
from plenipo.identity.route import declare_route
from plenipo.identity.store import AgentIdentity
from plenipo.identity.sync import sync_identity_with_core
from plenipo.route_defaults import default_route_service_fields
from plenipo.runtime.cursor import cursor_from_receipt_payload
from plenipo.runtime.events import (
    AgentEvent,
    ConnectEvent,
    DeliveryReceiptEvent,
    DisconnectEvent,
    ErrorEvent,
    MessageEvent,
)
from plenipo.runtime.state import (
    load_runtime_state,
    update_message_cursor,
    update_receipt_cursor,
)
from plenipo.runtime.store import OutboxRecord, ReceiptRecord, RuntimeStore
from plenipo.runtime.inbox_crypto import (
    PLAINTEXT_ALG,
    encrypt_plaintext,
    resolve_sidecar_store_key,
)


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


@dataclass
class PlenipoAgentRuntime:
    """Long-lived autonomous agent runtime with durable outbox and receipt recovery."""

    store_plaintext: bool = False
    _identity: AgentIdentity | None = field(default=None, init=False)
    _client: PlenipoClient | None = field(default=None, init=False)
    _store: RuntimeStore = field(default_factory=RuntimeStore, init=False)
    _events: asyncio.Queue[AgentEvent] = field(default_factory=asyncio.Queue, init=False)
    _running: bool = field(default=False, init=False)
    _reconnect_task: asyncio.Task[None] | None = field(default=None, init=False)
    _seen_receipt_ids: set[str] = field(default_factory=set, init=False)
    _route_declared: bool = field(default=False, init=False)

    @property
    def store(self) -> RuntimeStore:
        """Returns the durable runtime store."""
        return self._store

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
        await self.close()

    async def ensure_ready(self) -> AgentIdentity:
        """Loads identity, syncs with Core, ensures route metadata, and connects."""
        load_runtime_state(self._store)
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
        *,
        envelope_id: str | None = None,
    ) -> SendAck:
        """Sends an encrypted paid message with durable outbox tracking."""
        envelope_id = envelope_id or _generate_ulid()
        existing = self._store.get_outbox(envelope_id)
        if existing is not None and existing.status in ('accepted', 'delivered'):
            return _ack_from_outbox(existing)

        client = await self._ensure_client()
        self._store.insert_outbox_pending(
            envelope_id=envelope_id,
            recipient_did=recipient_did,
            recipient_document_url=recipient_document_url,
        )

        try:
            enc_key = await resolve_enc_public_key(
                recipient_did,
                recipient_document_url=recipient_document_url,
                registry_url=self._identity.registry_url if self._identity else None,
                relay_http_url=client.relay_http_url,
            )
            ack = await client.send(
                recipient_did,
                message,
                enc_key,
                envelope_id=envelope_id,
            )
            self._store.mark_outbox_accepted(
                envelope_id,
                ciphertext_bytes=_optional_int(ack.get('ciphertext_bytes')),
                billable_kb=_optional_int(ack.get('billable_kb')),
                charged_tokens=_optional_int(ack.get('charged_tokens')),
                balance_after=_optional_int(ack.get('balance_after')),
            )
            return ack
        except Exception as exc:
            self._store.mark_outbox_failed(envelope_id, last_error=str(exc))
            raise

    async def list_receipts(
        self,
        *,
        since: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetches persisted delivery receipts for this sender."""
        client = await self._ensure_client()
        result = await client.list_receipts(since=since, cursor=cursor, limit=limit)
        receipts = result.get('receipts', [])
        if not isinstance(receipts, list):
            return []
        return receipts

    def outbox(self, *, status: str | None = None, limit: int = 100) -> list[OutboxRecord]:
        """Returns sanitized local outbox rows."""
        return self._store.list_outbox(status=status, limit=limit)

    def receipts(self, *, limit: int = 100) -> list[ReceiptRecord]:
        """Returns sanitized local receipt rows."""
        return self._store.list_receipts(limit=limit)

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
            self._observe_message(envelope, plaintext=plaintext)

        def on_receipt(payload: dict[str, Any]) -> None:
            self._observe_receipt(payload, recovered=False)

        client.on_message(on_message)
        client.on_receipt(on_receipt)
        await client.connect()
        self._client = client
        await self._recover_missed_receipts()
        self._events.put_nowait(ConnectEvent(did=self._identity.did))

    def _observe_message(
        self,
        envelope: dict[str, Any],
        *,
        plaintext: str | None,
    ) -> None:
        envelope_id = str(envelope.get('envelope_id', ''))
        if not envelope_id:
            return

        received_at = str(envelope.get('created_at') or _utc_now_iso())
        sender_did = str(envelope.get('sender_did') or '')
        recipient_did = str(envelope.get('recipient_did') or '')

        if plaintext is not None and not self._store.has_sidecar_event(envelope_id, 'message'):
            store_key = resolve_sidecar_store_key()
            ciphertext_b64, nonce_b64 = encrypt_plaintext(plaintext, store_key)
            self._store.insert_inbox_message(
                envelope_id=envelope_id,
                sender_did=sender_did,
                recipient_did=recipient_did,
                received_at=received_at,
                plaintext_ciphertext=ciphertext_b64,
                plaintext_nonce=nonce_b64,
                plaintext_alg=PLAINTEXT_ALG,
                metadata={'created_at': envelope.get('created_at')},
            )
            self._store.insert_sidecar_event(
                event_type='message',
                envelope_id=envelope_id,
                payload={
                    'type': 'message',
                    'envelope_id': envelope_id,
                    'sender_did': sender_did,
                    'recipient_did': recipient_did,
                    'received_at': received_at,
                    'plaintext_ref': f'inbox:{envelope_id}',
                },
            )
            update_message_cursor(
                received_at=received_at,
                envelope_id=envelope_id,
                store=self._store,
            )

        self._events.put_nowait(
            MessageEvent(
                envelope_id=envelope_id,
                sender_did=sender_did,
                recipient_did=recipient_did,
                plaintext=plaintext,
                created_at=envelope.get('created_at'),
            )
        )

    def _observe_receipt(self, payload: dict[str, Any], *, recovered: bool) -> None:
        envelope_id = str(payload.get('envelope_id', ''))
        if not envelope_id:
            return

        sender_did = self._identity.did if self._identity else str(payload.get('sender_did') or '')
        if self._store.has_receipt(envelope_id):
            if envelope_id not in self._seen_receipt_ids:
                self._seen_receipt_ids.add(envelope_id)
            return

        is_new = self._store.upsert_receipt(payload, sender_did=sender_did)
        if not is_new:
            return

        self._seen_receipt_ids.add(envelope_id)
        self._store.mark_outbox_delivered(
            envelope_id,
            delivered_at=str(payload.get('delivered_at') or payload.get('received_at') or '') or None,
        )
        if not self._store.has_sidecar_event(envelope_id, 'delivery_receipt'):
            receipt_payload: dict[str, Any] = {
                'type': 'delivery_receipt',
                'envelope_id': envelope_id,
                'charged_tokens': _optional_int(payload.get('charged_tokens')),
            }
            delivered_at = payload.get('delivered_at') or payload.get('received_at')
            if delivered_at:
                receipt_payload['delivered_at'] = delivered_at
            if payload.get('ciphertext_bytes') is not None:
                receipt_payload['ciphertext_bytes'] = _optional_int(payload.get('ciphertext_bytes'))
            if payload.get('billable_kb') is not None:
                receipt_payload['billable_kb'] = _optional_int(payload.get('billable_kb'))
            if payload.get('balance_after') is not None:
                receipt_payload['balance_after'] = _optional_int(payload.get('balance_after'))
            self._store.insert_sidecar_event(
                event_type='delivery_receipt',
                envelope_id=envelope_id,
                payload=receipt_payload,
            )
        event = self._receipt_event_from_payload(payload, recovered=recovered)
        self._events.put_nowait(event)
        update_receipt_cursor(
            delivered_at=event.delivered_at,
            received_at=event.received_at,
            cursor=cursor_from_receipt_payload(payload),
            store=self._store,
        )

    async def _recover_missed_receipts(self) -> None:
        if self._client is None or self._identity is None:
            return

        cursor = self._store.get_state('last_receipt_cursor')
        state = load_runtime_state(self._store)
        since = None if cursor else state.last_receipt_seen_at
        page_cursor = cursor

        while True:
            result = await self._client.list_receipts(
                cursor=page_cursor,
                since=since,
                limit=100,
            )
            receipts = result.get('receipts', [])
            if not isinstance(receipts, list):
                break

            for payload in receipts:
                if isinstance(payload, dict):
                    self._observe_receipt(payload, recovered=True)

            next_cursor = result.get('next_cursor')
            if not receipts or not next_cursor:
                if receipts:
                    last = receipts[-1]
                    if isinstance(last, dict):
                        final_cursor = cursor_from_receipt_payload(last)
                        if final_cursor:
                            self._store.set_state('last_receipt_cursor', final_cursor)
                break

            page_cursor = str(next_cursor)
            since = None

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

    async def close(self) -> None:
        """Disconnects relay and closes the local SQLite store."""
        await self.disconnect()
        self._store.close()

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


def _ack_from_outbox(row: OutboxRecord) -> SendAck:
    return SendAck(
        type='ack',
        envelope_id=row.envelope_id,
        status='queued',
        ciphertext_bytes=row.ciphertext_bytes,
        billable_kb=row.billable_kb,
        charged_tokens=row.charged_tokens,
        balance_after=row.balance_after,
    )


def _document_has_route(document: dict[str, Any]) -> bool:
    for service in document.get('service') or []:
        if service.get('type') == 'PlenipoAgent' and service.get('protocols'):
            return True
    return False
