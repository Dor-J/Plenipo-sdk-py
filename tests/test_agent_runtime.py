"""Tests for Agent Runtime v0."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from plenipo.crypto import base64url
from plenipo.identity.sync import SyncIdentityResult
from plenipo.runtime.agent import PlenipoAgentRuntime
from plenipo.runtime.events import ConnectEvent, DeliveryReceiptEvent, MessageEvent
from plenipo.runtime.state import RuntimeState, load_runtime_state, save_runtime_state


class FakeClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.relay_http_url = 'http://relay.local'
        self.connected = False
        self.message_handler = None
        self.receipt_handler = None
        self.list_calls: list[dict[str, Any]] = []

    def on_message(self, handler: object) -> None:
        self.message_handler = handler

    def on_receipt(self, handler: object) -> None:
        self.receipt_handler = handler

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def send(
        self,
        recipient_did: str,
        message: str,
        enc_key: bytes,
        *,
        envelope_id: str | None = None,
    ) -> dict[str, object]:
        return {
            'envelope_id': envelope_id or '01SEND',
            'ciphertext_bytes': 105,
            'billable_kb': 1,
            'charged_tokens': 1,
            'balance_after': 999,
        }

    async def list_receipts(
        self,
        *,
        since: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        self.list_calls.append({'since': since, 'cursor': cursor, 'limit': limit})
        return {
            'type': 'receipt.list.result',
            'receipts': [
                {
                    'type': 'delivery_receipt',
                    'envelope_id': '01RCPT',
                    'ciphertext_bytes': 105,
                    'billable_kb': 1,
                    'charged_tokens': 1,
                    'balance_after': 999,
                    'delivered_at': '2026-06-08T20:56:01Z',
                }
            ],
            'next_cursor': None,
        }


def _identity() -> object:
    from plenipo.identity.store import identity_from_create_result

    return identity_from_create_result(
        did='did:web:localhost:agents:runtime-test',
        auth_secret_b64=base64url.encode(b'\x01' * 32),
        enc_secret_b64=base64url.encode(b'\x02' * 32),
        did_document_url='http://localhost:4000/v1/dids?did=did%3Aweb%3Alocalhost%3Aagents%3Aruntime-test',
        document={
            'id': 'did:web:localhost:agents:runtime-test',
            'service': [
                {
                    'type': 'PlenipoAgent',
                    'protocols': ['plenipo.message.v1'],
                    'capabilities': ['general', 'mcp'],
                }
            ],
        },
        relay_url='ws://localhost:4000/agent/websocket',
        registry_url='http://localhost:4001',
        core_url='http://localhost:4000',
        did_document_mode='core_hosted',
        core_registered=True,
        registration_pending=False,
    )


async def _patch_runtime(monkeypatch: pytest.MonkeyPatch, identity: object) -> list[FakeClient]:
    created: list[FakeClient] = []

    def client_factory(**kwargs: object) -> FakeClient:
        client = FakeClient(**kwargs)
        created.append(client)
        return client

    async def fake_ensure_identity() -> object:
        return identity

    async def fake_sync(current: object, *_args: object, **_kwargs: object) -> tuple[object, SyncIdentityResult]:
        identity = current
        return identity, SyncIdentityResult(
            ok=True,
            did=identity.did,
            core_registered=True,
            registration_pending=False,
            document_fingerprint=None,
            warnings=[],
        )

    monkeypatch.setattr('plenipo.runtime.agent.ensure_identity', fake_ensure_identity)
    monkeypatch.setattr('plenipo.runtime.agent.sync_identity_with_core', fake_sync)
    monkeypatch.setattr('plenipo.runtime.agent.PlenipoClient', client_factory)
    return created


async def test_runtime_recovers_missed_receipts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    save_runtime_state(RuntimeState(last_receipt_seen_at='2026-06-08T20:56:00Z'))

    identity = _identity()
    created = await _patch_runtime(monkeypatch, identity)

    runtime = PlenipoAgentRuntime()
    await runtime.ensure_ready()

    assert created[0].list_calls == [{'since': '2026-06-08T20:56:00Z', 'cursor': None, 'limit': 100}]

    startup_events: list[object] = []
    for _ in range(2):
        startup_events.append(await asyncio.wait_for(runtime._events.get(), timeout=1.0))

    receipt_event = next(e for e in startup_events if isinstance(e, DeliveryReceiptEvent))
    assert isinstance(next(e for e in startup_events if isinstance(e, ConnectEvent)), ConnectEvent)
    assert receipt_event.envelope_id == '01RCPT'
    assert receipt_event.recovered is True
    assert receipt_event.charged_tokens == 1

    state = load_runtime_state()
    assert state.last_receipt_seen_at == '2026-06-08T20:56:01Z'


async def test_runtime_emits_message_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    identity = _identity()
    created = await _patch_runtime(monkeypatch, identity)

    runtime = PlenipoAgentRuntime()
    await runtime.ensure_ready()

    while not runtime._events.empty():
        event = runtime._events.get_nowait()
        if isinstance(event, ConnectEvent):
            break

    assert created[0].message_handler is not None
    created[0].message_handler(
        {
            'envelope_id': '01MSG',
            'sender_did': 'did:web:localhost:agents:sender',
            'recipient_did': identity.did,
            'ciphertext': 'not-valid',
        }
    )

    event = await asyncio.wait_for(runtime._events.get(), timeout=1.0)
    assert isinstance(event, MessageEvent)
    assert event.envelope_id == '01MSG'


async def test_runtime_send_persists_outbox(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    identity = _identity()
    await _patch_runtime(monkeypatch, identity)

    async def fake_resolve(*_args: object, **_kwargs: object) -> bytes:
        return b'k' * 32

    monkeypatch.setattr('plenipo.runtime.agent.resolve_enc_public_key', fake_resolve)

    runtime = PlenipoAgentRuntime()
    await runtime.ensure_ready()
    while not runtime._events.empty():
        runtime._events.get_nowait()

    ack = await runtime.send('did:web:localhost:agents:recipient', 'hello')
    row = runtime.store.get_outbox(str(ack['envelope_id']))
    assert row is not None
    assert row.status == 'accepted'
    assert row.charged_tokens == 1
    runtime.store.close()
