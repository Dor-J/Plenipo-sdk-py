"""Tests for Plenipo Agent Sidecar v0.2."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

from plenipo.agent.cli import main
from plenipo.discover.records import RouteRecord
from plenipo.identity.store import AgentIdentity
from plenipo.runtime.events import DeliveryReceiptEvent, MessageEvent
from plenipo.runtime.store import OutboxRecord, ReceiptRecord, RuntimeStore
from plenipo.sidecar.api import SidecarApp
from plenipo.sidecar.config import SidecarConfig, validate_bind_host
from plenipo.sidecar.events import EventBuffer
from plenipo.sidecar.models import (
    SERVICE_NAME,
    SIDECAR_VERSION,
    contains_secret_keys,
    event_to_dict,
)


@dataclass
class FakeRuntime:
    """Minimal runtime stub for sidecar API tests."""

    _identity: AgentIdentity | None = None
    _client: Any = None
    _store: RuntimeStore = field(default_factory=lambda: RuntimeStore())
    send_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def store(self) -> RuntimeStore:
        return self._store

    async def send(
        self,
        recipient_did: str,
        message: str,
        recipient_document_url: str | None = None,
        *,
        envelope_id: str | None = None,
    ) -> dict[str, Any]:
        self.send_calls.append(
            {
                'recipient_did': recipient_did,
                'message': message,
                'recipient_document_url': recipient_document_url,
                'envelope_id': envelope_id,
            }
        )
        return {
            'envelope_id': envelope_id or '01ENVELOPE',
            'ciphertext_bytes': 105,
            'billable_kb': 1,
            'charged_tokens': 1,
            'balance_after': 999,
        }

    def outbox(self, *, status: str | None = None, limit: int = 100) -> list[OutboxRecord]:
        return self._store.list_outbox(status=status, limit=limit)

    def receipts(self, *, limit: int = 100) -> list[ReceiptRecord]:
        return self._store.list_receipts(limit=limit)


def _fake_identity(tmp_path) -> AgentIdentity:  # type: ignore[no-untyped-def]
    document = {
        'id': 'did:web:localhost:agents:test',
        'service': [
            {
                'type': 'PlenipoAgent',
                'protocols': ['plenipo.message.v1'],
                'capabilities': ['general', 'mcp'],
                'payment': {'model': 'per_kb', 'price_per_kb_tokens': 1, 'accepted_schemes': ['plenipo-dev-token']},
                'limits': {'max_message_kb': 256, 'offline_queue_ttl_seconds': 86400},
                'encryption': {'alg': 'nacl-sealedbox-v1', 'publicKeyRef': '#enc-key'},
            }
        ],
    }
    return AgentIdentity(
        did='did:web:localhost:agents:test',
        auth_secret_b64='secret-auth',
        enc_secret_b64='secret-enc',
        did_document_url='http://127.0.0.1:4000/v1/dids/did:web:localhost:agents:test',
        relay_url='ws://127.0.0.1:4000/agent/websocket',
        registry_url='http://127.0.0.1:4001',
        core_url='http://127.0.0.1:4000',
        capabilities=['general', 'mcp'],
        created_at='2026-01-01T00:00:00Z',
        document=document,
        core_registered=True,
    )


@pytest.fixture
def sidecar_setup(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    runtime = FakeRuntime(_identity=_fake_identity(tmp_path))
    runtime._store = RuntimeStore(tmp_path / 'runtime.sqlite')
    runtime._client = type('Conn', (), {'connected': True})()
    buffer = EventBuffer(max_size=100)
    app = SidecarApp(runtime, buffer).create_app()
    client = TestClient(app)
    return client, runtime, buffer


@pytest.fixture
def sidecar_client(sidecar_setup):  # type: ignore[no-untyped-def]
    client, _runtime, _buffer = sidecar_setup
    return client


def test_health_returns_ok(sidecar_client: TestClient) -> None:
    response = sidecar_client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert body['service'] == SERVICE_NAME
    assert body['version'] == SIDECAR_VERSION


def test_status_hides_secrets(sidecar_client: TestClient) -> None:
    response = sidecar_client.get('/status')
    assert response.status_code == 200
    body = response.json()
    assert body['did'] == 'did:web:localhost:agents:test'
    assert body['connected'] is True
    assert body['core_registered'] is True
    assert body['route_declared'] is True
    assert 'outbox' in body
    assert 'receipts' in body
    assert not contains_secret_keys(body)
    assert 'secret-auth' not in response.text
    assert 'secret-enc' not in response.text


def test_send_calls_runtime_and_returns_billing(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, runtime, _buffer = sidecar_setup
    response = client.post(
        '/send',
        json={'recipient_did': 'did:web:localhost:agents:peer', 'message': 'hello'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['envelope_id'] == '01ENVELOPE'
    assert body['ciphertext_bytes'] == 105
    assert body['billable_kb'] == 1
    assert body['charged_tokens'] == 1
    assert body['balance_after'] == 999
    assert body['status'] == 'accepted'
    assert runtime.send_calls[0]['message'] == 'hello'


def test_discover_passes_filters(monkeypatch, sidecar_client: TestClient) -> None:
    captured: dict[str, Any] = {}

    async def fake_discover(**kwargs: Any) -> list[RouteRecord]:
        captured.update(kwargs)
        return [
            {
                'did': 'did:web:localhost:agents:peer',
                'document_url': 'http://127.0.0.1:4000/v1/dids/did:web:localhost:agents:peer',
                'protocols': ['plenipo.message.v1'],
                'capabilities': ['mcp'],
            }
        ]

    monkeypatch.setattr('plenipo.sidecar.api.discover_agents', fake_discover)
    response = sidecar_client.get(
        '/discover?capability=mcp&protocol=plenipo.message.v1&limit=5&online=true'
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body['results']) == 1
    assert captured['capability'] == 'mcp'
    assert captured['protocol'] == 'plenipo.message.v1'
    assert captured['limit'] == 5
    assert captured['online'] is True


def test_outbox_returns_sanitized_rows(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, runtime, _buffer = sidecar_setup
    runtime._store.insert_outbox_pending(
        envelope_id='01OUT',
        recipient_did='did:web:localhost:agents:peer',
    )
    runtime._store.mark_outbox_accepted(
        '01OUT',
        ciphertext_bytes=10,
        billable_kb=1,
        charged_tokens=1,
        balance_after=99,
    )

    response = client.get('/outbox')
    assert response.status_code == 200
    rows = response.json()['outbox']
    assert len(rows) == 1
    assert rows[0]['envelope_id'] == '01OUT'
    assert rows[0]['status'] == 'accepted'
    assert not contains_secret_keys(rows)


def test_receipts_returns_sanitized_rows(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, runtime, _buffer = sidecar_setup
    runtime._store.upsert_receipt(
        {
            'envelope_id': '01RCPT',
            'recipient_did': 'did:web:localhost:agents:peer',
            'ciphertext_bytes': 20,
            'billable_kb': 1,
            'charged_tokens': 1,
            'balance_after': 98,
            'delivered_at': '2026-01-01T00:00:01Z',
        },
        sender_did='did:web:localhost:agents:test',
    )

    response = client.get('/receipts')
    assert response.status_code == 200
    rows = response.json()['receipts']
    assert len(rows) == 1
    assert rows[0]['envelope_id'] == '01RCPT'
    assert rows[0]['charged_tokens'] == 1
    assert not contains_secret_keys(rows)


@pytest.mark.asyncio
async def test_events_long_poll_returns_message_and_receipt() -> None:
    buffer = EventBuffer(max_size=100)

    async def produce() -> None:
        await asyncio.sleep(0.05)
        buffer.append_runtime_event(
            MessageEvent(
                envelope_id='01MSG',
                sender_did='did:web:localhost:agents:sender',
                plaintext='hello',
            )
        )
        async with buffer._condition:
            buffer._condition.notify_all()
        await asyncio.sleep(0.05)
        buffer.append_runtime_event(
            DeliveryReceiptEvent(
                envelope_id='01RCPT',
                charged_tokens=1,
                delivered_at='2026-01-01T00:00:01Z',
            )
        )
        async with buffer._condition:
            buffer._condition.notify_all()

    producer = asyncio.create_task(produce())
    matches = await buffer.wait_for_events(since_id=0, timeout_ms=2000, limit=10)
    assert len(matches) >= 1
    assert matches[0].payload['type'] == 'message'

    matches2 = await buffer.wait_for_events(
        since_id=matches[0].event_id,
        timeout_ms=2000,
        limit=10,
    )
    assert any(item.payload['type'] == 'delivery_receipt' for item in matches2)
    await producer


def test_events_endpoint_returns_buffered_events(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, _runtime, buffer = sidecar_setup
    buffer.append_runtime_event(
        MessageEvent(envelope_id='01MSG', sender_did='did:web:localhost:agents:sender', plaintext='hi')
    )

    response = client.get('/events?timeout_ms=100&limit=10')
    assert response.status_code == 200
    body = response.json()
    assert len(body['events']) == 1
    assert body['events'][0]['type'] == 'message'
    assert body['events'][0]['plaintext'] == 'hi'


def test_non_localhost_bind_requires_flag() -> None:
    with pytest.raises(ValueError, match='allow-remote-bind'):
        validate_bind_host('0.0.0.0', allow_remote_bind=False)

    validate_bind_host('0.0.0.0', allow_remote_bind=True)


def test_cli_sidecar_rejects_remote_bind_without_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr('plenipo.sidecar.server.run_sidecar', lambda config: 0)
    assert main(['sidecar', '--host', '0.0.0.0']) == 2


def test_send_plaintext_not_logged(caplog, sidecar_client: TestClient) -> None:
    caplog.set_level(logging.INFO)
    secret_message = 'super-secret-payload'
    sidecar_client.post(
        '/send',
        json={'recipient_did': 'did:web:localhost:agents:peer', 'message': secret_message},
    )
    assert secret_message not in caplog.text


def test_event_to_dict_maps_message_and_receipt() -> None:
    message = event_to_dict(
        MessageEvent(envelope_id='01MSG', sender_did='did:web:localhost:agents:a', plaintext='x')
    )
    assert message is not None
    assert message['type'] == 'message'

    receipt = event_to_dict(
        DeliveryReceiptEvent(envelope_id='01RCPT', charged_tokens=1, delivered_at='t')
    )
    assert receipt is not None
    assert receipt['type'] == 'delivery_receipt'


def test_sidecar_config_defaults() -> None:
    config = SidecarConfig()
    assert config.host == '127.0.0.1'
    assert config.port == 8787
