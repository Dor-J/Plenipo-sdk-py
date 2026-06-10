"""Tests for Plenipo Agent Sidecar v0.2.1 security and API."""

from __future__ import annotations

import asyncio
import logging
import os
import stat
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

from plenipo.agent.cli import main
from plenipo.discover.records import RouteRecord
from plenipo.identity.store import AgentIdentity
from plenipo.runtime.store import OutboxRecord, ReceiptRecord, RuntimeStore
from plenipo.sidecar.api import SidecarApp
from plenipo.sidecar.auth import (
    read_sidecar_token_file,
    resolve_sidecar_token,
    write_sidecar_token_file,
)
from plenipo.sidecar.client import PlenipoSidecarClient
from plenipo.sidecar.config import (
    NO_AUTH_WARNING,
    SidecarConfig,
    SidecarSecurity,
    load_sidecar_config_file,
    resolve_sidecar_config,
    validate_bind_host,
    validate_no_auth_bind,
    validate_tls_config,
)
from plenipo.sidecar.events import EventBuffer
from plenipo.sidecar.middleware import build_signed_request_headers
from plenipo.sidecar.models import (
    SERVICE_NAME,
    SIDECAR_VERSION,
    contains_secret_keys,
)

TEST_TOKEN = 'test-bearer-token-secret'


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
                'payment': {
                    'model': 'per_kb',
                    'price_per_kb_tokens': 1,
                    'accepted_schemes': ['plenipo-prepaid-token'],
                },
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


def _auth_headers(token: str = TEST_TOKEN) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _make_security(
    *,
    auth_enabled: bool = True,
    token: str | None = TEST_TOKEN,
    allowed_origins: frozenset[str] = frozenset(),
    signed_request_secret: str | None = None,
) -> SidecarSecurity:
    return SidecarSecurity(
        auth_enabled=auth_enabled,
        token=token,
        allowed_origins=allowed_origins,
        signed_request_secret=signed_request_secret,
    )


@pytest.fixture
def sidecar_setup(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    runtime = FakeRuntime(_identity=_fake_identity(tmp_path))
    runtime._store = RuntimeStore(tmp_path / 'runtime.sqlite')
    runtime._client = type('Conn', (), {'connected': True})()
    buffer = EventBuffer(store=runtime._store)
    security = _make_security()
    app = SidecarApp(runtime, buffer, security).create_app()
    client = TestClient(app)
    return client, runtime, buffer, security


@pytest.fixture
def sidecar_client(sidecar_setup):  # type: ignore[no-untyped-def]
    client, _runtime, _buffer, _security = sidecar_setup
    return client


def test_health_returns_ok_without_auth(sidecar_client: TestClient) -> None:
    response = sidecar_client.get('/health')
    assert response.status_code == 200
    body = response.json()
    assert body['ok'] is True
    assert body['service'] == SERVICE_NAME
    assert body['version'] == SIDECAR_VERSION


def test_status_fails_without_token(sidecar_client: TestClient) -> None:
    response = sidecar_client.get('/status')
    assert response.status_code == 401


def test_metrics_requires_token(sidecar_client: TestClient) -> None:
    response = sidecar_client.get('/metrics')
    assert response.status_code == 401


def test_metrics_returns_sanitized_prometheus_text(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, runtime, _buffer, _security = sidecar_setup
    runtime._store.insert_outbox_pending(
        envelope_id='01METRIC',
        recipient_did='did:web:localhost:agents:peer',
    )
    runtime._store.insert_sidecar_event(
        event_type='message',
        envelope_id='01METRIC',
        payload={'plaintext': 'super-secret-local-message'},
    )

    response = client.get('/metrics', headers=_auth_headers())

    assert response.status_code == 200
    text = response.text
    assert 'plenipo_sidecar_build_info' in text
    assert 'plenipo_sidecar_outbox_rows{status="pending"} 1' in text
    assert 'plenipo_sidecar_events{event_type="message"} 1' in text
    assert 'super-secret-local-message' not in text
    assert TEST_TOKEN not in text


def test_status_works_with_valid_token(sidecar_client: TestClient) -> None:
    response = sidecar_client.get('/status', headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body['did'] == 'did:web:localhost:agents:test'
    assert not contains_secret_keys(body)


def test_invalid_token_returns_401(sidecar_client: TestClient) -> None:
    response = sidecar_client.get('/status', headers=_auth_headers('wrong-token'))
    assert response.status_code == 401


def test_send_requires_token(sidecar_client: TestClient) -> None:
    response = sidecar_client.post(
        '/send',
        json={'recipient_did': 'did:web:localhost:agents:peer', 'message': 'hello'},
    )
    assert response.status_code == 401


def test_signed_request_mode_rejects_unsigned_send(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    runtime = FakeRuntime(_identity=_fake_identity(tmp_path))
    runtime._client = type('Conn', (), {'connected': True})()
    security = _make_security(signed_request_secret='signing-secret')
    store = RuntimeStore(tmp_path / 'runtime.sqlite')
    app = SidecarApp(runtime, EventBuffer(store=store), security).create_app()
    client = TestClient(app)

    response = client.post(
        '/send',
        json={'recipient_did': 'did:web:localhost:agents:peer', 'message': 'hello'},
        headers=_auth_headers(),
    )

    assert response.status_code == 401


def test_signed_request_mode_accepts_signed_send(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    runtime = FakeRuntime(_identity=_fake_identity(tmp_path))
    runtime._client = type('Conn', (), {'connected': True})()
    security = _make_security(signed_request_secret='signing-secret')
    store = RuntimeStore(tmp_path / 'runtime.sqlite')
    app = SidecarApp(runtime, EventBuffer(store=store), security).create_app()
    client = TestClient(app)
    body = b'{"recipient_did":"did:web:localhost:agents:peer","message":"hello"}'

    response = client.post(
        '/send',
        content=body,
        headers={
            **_auth_headers(),
            'Content-Type': 'application/json',
            **build_signed_request_headers('signing-secret', 'POST', '/send', body),
        },
    )

    assert response.status_code == 200
    assert runtime.send_calls[0]['message'] == 'hello'


def test_send_calls_runtime_and_returns_billing(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, runtime, _buffer, _security = sidecar_setup
    response = client.post(
        '/send',
        json={'recipient_did': 'did:web:localhost:agents:peer', 'message': 'hello'},
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    body = response.json()
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
        '/discover?capability=mcp&protocol=plenipo.message.v1&limit=5&online=true',
        headers=_auth_headers(),
    )
    assert response.status_code == 200
    assert captured['capability'] == 'mcp'


def test_outbox_returns_sanitized_rows(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, runtime, _buffer, _security = sidecar_setup
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
    response = client.get('/outbox', headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()['outbox'][0]['envelope_id'] == '01OUT'


def test_receipts_returns_sanitized_rows(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    client, runtime, _buffer, _security = sidecar_setup
    runtime._store.upsert_receipt(
        {
            'envelope_id': '01RCPT',
            'recipient_did': 'did:web:localhost:agents:peer',
            'charged_tokens': 1,
            'delivered_at': '2026-01-01T00:00:01Z',
        },
        sender_did='did:web:localhost:agents:test',
    )
    response = client.get('/receipts', headers=_auth_headers())
    assert response.status_code == 200
    assert response.json()['receipts'][0]['envelope_id'] == '01RCPT'


def test_events_endpoint_returns_buffered_events(sidecar_setup) -> None:  # type: ignore[no-untyped-def]
    from plenipo.runtime.inbox_crypto import PLAINTEXT_ALG, encrypt_plaintext, resolve_sidecar_store_key

    client, runtime, _buffer, _security = sidecar_setup
    key = resolve_sidecar_store_key()
    ciphertext_b64, nonce_b64 = encrypt_plaintext('hi', key)
    runtime._store.insert_inbox_message(
        envelope_id='01MSG',
        sender_did='did:web:localhost:agents:sender',
        recipient_did='did:web:localhost:agents:test',
        received_at='2026-06-09T00:00:00Z',
        plaintext_ciphertext=ciphertext_b64,
        plaintext_nonce=nonce_b64,
        plaintext_alg=PLAINTEXT_ALG,
        metadata={},
    )
    runtime._store.insert_sidecar_event(
        event_type='message',
        envelope_id='01MSG',
        payload={
            'type': 'message',
            'envelope_id': '01MSG',
            'sender_did': 'did:web:localhost:agents:sender',
            'recipient_did': 'did:web:localhost:agents:test',
            'received_at': '2026-06-09T00:00:00Z',
            'plaintext_ref': 'inbox:01MSG',
        },
    )
    response = client.get('/events?timeout_ms=100&limit=10', headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body['events'][0]['plaintext'] == 'hi'
    assert body['next_after_id'] == body['events'][0]['id']


def test_no_auth_allows_requests_locally(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    runtime = FakeRuntime(_identity=_fake_identity(tmp_path))
    runtime._client = type('Conn', (), {'connected': True})()
    store = RuntimeStore(tmp_path / 'runtime.sqlite')
    app = SidecarApp(
        runtime,
        EventBuffer(store=store),
        _make_security(auth_enabled=False, token=None),
    ).create_app()
    client = TestClient(app)
    assert client.get('/status').status_code == 200


def test_no_auth_non_localhost_bind_rejected() -> None:
    with pytest.raises(ValueError, match='--no-auth cannot be used'):
        validate_no_auth_bind('0.0.0.0', no_auth=True)


def test_cli_sidecar_rejects_no_auth_remote_bind(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assert main(['sidecar', '--host', '0.0.0.0', '--no-auth', '--allow-remote-bind']) == 2


def test_token_file_generated_with_restrictive_permissions(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    monkeypatch.delenv('PLENIPO_SIDECAR_TOKEN', raising=False)
    token, path, generated = resolve_sidecar_token(generate_if_missing=True)
    assert generated is True
    assert token is not None
    assert path is not None
    assert read_sidecar_token_file(path) == token
    if os.name != 'nt':
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600


def test_env_token_override(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    monkeypatch.setenv('PLENIPO_SIDECAR_TOKEN', 'env-token-value')
    token, _path, generated = resolve_sidecar_token()
    assert token == 'env-token-value'
    assert generated is False


def test_cli_token_path_command(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    write_sidecar_token_file('cli-token-value')
    printed: list[str] = []
    monkeypatch.setattr('builtins.print', lambda *args, **kwargs: printed.append(' '.join(str(a) for a in args)))
    assert main(['sidecar-token']) == 0
    output = '\n'.join(printed)
    assert 'Token file:' in output
    assert 'Exists: true' in output
    assert 'cli-token-value' not in output


def test_cli_token_show_prints_token(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    write_sidecar_token_file('shown-token')
    stdout: list[str] = []
    stderr: list[str] = []
    monkeypatch.setattr('builtins.print', lambda *args, **kwargs: (
        stderr if kwargs.get('file') is __import__('sys').stderr else stdout
    ).append(' '.join(str(a) for a in args)))
    assert main(['sidecar-token', '--show']) == 0
    assert any('WARNING' in line for line in stderr)
    assert 'shown-token' in stdout


def test_cors_default_has_no_wildcard(sidecar_client: TestClient) -> None:
    response = sidecar_client.get(
        '/status',
        headers={**_auth_headers(), 'Origin': 'http://evil.example'},
    )
    assert response.status_code == 403
    assert response.headers.get('access-control-allow-origin') != '*'


def test_cors_disallowed_origin_rejected(sidecar_client: TestClient) -> None:
    response = sidecar_client.get(
        '/status',
        headers={**_auth_headers(), 'Origin': 'http://127.0.0.1:9999'},
    )
    assert response.status_code == 403


def test_cors_allowed_origin_accepted(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    runtime = FakeRuntime(_identity=_fake_identity(tmp_path))
    runtime._client = type('Conn', (), {'connected': True})()
    security = _make_security(allowed_origins=frozenset({'http://127.0.0.1:3000'}))
    store = RuntimeStore(tmp_path / 'runtime.sqlite')
    app = SidecarApp(runtime, EventBuffer(store=store), security).create_app()
    client = TestClient(app)
    response = client.get(
        '/status',
        headers={**_auth_headers(), 'Origin': 'http://127.0.0.1:3000'},
    )
    assert response.status_code == 200
    assert response.headers.get('access-control-allow-origin') == 'http://127.0.0.1:3000'


def test_authorization_header_not_logged(caplog, sidecar_client: TestClient) -> None:
    caplog.set_level(logging.INFO, logger='plenipo.sidecar.access')
    sidecar_client.get('/status', headers=_auth_headers('super-secret-bearer'))
    assert TEST_TOKEN not in caplog.text
    assert 'super-secret-bearer' not in caplog.text
    assert 'Authorization' not in caplog.text


def test_send_body_not_logged(caplog, sidecar_client: TestClient) -> None:
    caplog.set_level(logging.INFO, logger='plenipo.sidecar.access')
    secret_message = 'super-secret-payload'
    sidecar_client.post(
        '/send',
        json={'recipient_did': 'did:web:localhost:agents:peer', 'message': secret_message},
        headers=_auth_headers(),
    )
    assert secret_message not in caplog.text


def test_sidecar_client_calls_status_and_send(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: list[tuple[str, str, dict[str, Any]]] = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                'did': 'did:web:localhost:agents:test',
                'status': 'accepted',
                'events': [{'type': 'message'}],
                'since_id': 1,
            }

    def fake_request(
        _self: httpx.Client,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> FakeResponse:
        captured.append((method, path, kwargs))
        return FakeResponse()

    monkeypatch.setattr(httpx.Client, 'request', fake_request)
    sc = PlenipoSidecarClient(base_url='http://127.0.0.1:8787', token=TEST_TOKEN)
    sc.status()
    sc.send('did:web:localhost:agents:peer', 'hello')
    sc.events(timeout_ms=100)
    sc.close()

    assert captured[0][0] == 'GET'
    assert captured[0][1] == '/status'
    assert captured[0][2]['headers']['Authorization'] == f'Bearer {TEST_TOKEN}'
    assert captured[1][0] == 'POST'
    assert captured[1][1] == '/send'
    assert captured[2][0] == 'GET'
    assert captured[2][1] == '/events'


@pytest.mark.asyncio
async def test_events_long_poll_returns_message_and_receipt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    store = RuntimeStore(tmp_path / 'runtime.sqlite')
    buffer = EventBuffer(store=store)

    async def produce() -> None:
        await asyncio.sleep(0.05)
        store.insert_sidecar_event(
            event_type='delivery_receipt',
            envelope_id='01MSG',
            payload={
                'type': 'delivery_receipt',
                'envelope_id': '01MSG',
                'charged_tokens': 1,
            },
        )
        await buffer.notify()

    producer = asyncio.create_task(produce())
    events, next_after_id = await buffer.wait_for_events(
        after_id=0,
        timeout_ms=2000,
        limit=10,
        include_plaintext=False,
    )
    assert events[0]['type'] == 'delivery_receipt'
    assert next_after_id == events[0]['id']
    await producer


def test_non_localhost_bind_requires_flag() -> None:
    with pytest.raises(ValueError, match='allow-remote-bind'):
        validate_bind_host('0.0.0.0', allow_remote_bind=False)


def test_cli_sidecar_rejects_remote_bind_without_flag(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr('plenipo.sidecar.server.run_sidecar', lambda config: 0)
    assert main(['sidecar', '--host', '0.0.0.0']) == 2


def test_sidecar_config_defaults() -> None:
    config = SidecarConfig()
    assert config.host == '127.0.0.1'
    assert config.no_auth is False


def test_sidecar_config_file_env_and_cli_precedence(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / 'sidecar.toml'
    config_path.write_text(
        """
        [sidecar]
        host = "127.0.0.2"
        port = 9000
        capability = "file-cap"
        allow_remote_bind = false
        allowed_origins = ["http://file.example"]
        tls_cert = "/certs/file.crt"
        tls_key = "/certs/file.key"
        """,
        encoding='utf-8',
    )
    monkeypatch.setenv('PLENIPO_SIDECAR_PORT', '9100')
    monkeypatch.setenv('PLENIPO_SIDECAR_ALLOWED_ORIGINS', 'http://env.example')

    config = resolve_sidecar_config(
        config_path=config_path,
        cli_values={
            'host': '127.0.0.3',
            'capability': 'cli-cap',
            'allowed_origins': ('http://cli.example',),
        },
    )

    assert config.host == '127.0.0.3'
    assert config.port == 9100
    assert config.capability == 'cli-cap'
    assert config.allowed_origins == ('http://cli.example',)
    assert config.tls_cert == '/certs/file.crt'


def test_sidecar_config_loader_accepts_top_level_toml(tmp_path) -> None:  # type: ignore[no-untyped-def]
    config_path = tmp_path / 'sidecar.toml'
    config_path.write_text('host = "127.0.0.4"\n', encoding='utf-8')
    assert load_sidecar_config_file(config_path)['host'] == '127.0.0.4'


def test_sidecar_tls_requires_cert_and_key() -> None:
    with pytest.raises(ValueError, match='tls-cert'):
        validate_tls_config(SidecarConfig(tls_cert='/certs/local.crt'))


def test_no_auth_warning_message() -> None:
    assert '--no-auth' in NO_AUTH_WARNING
