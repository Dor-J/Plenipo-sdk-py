"""MCP runtime buffer tests."""

from plenipo.crypto import base64url
from plenipo.mcp.runtime import (
    BufferedMessage,
    McpRuntime,
    McpRuntimeConfig,
    get_mcp_runtime,
    reset_mcp_runtime,
)
import pytest


def test_drain_messages_since_and_limit() -> None:
    runtime = McpRuntime(
        McpRuntimeConfig(
            did='did:web:test.local',
            auth_secret_b64='AAAA',
            did_document_url='https://test.local/.well-known/did.json',
            relay_url='ws://localhost:4000/agent/websocket',
            enc_secret_b64=base64url.encode(b'\x02' * 32),
        )
    )
    runtime._buffer = [
        BufferedMessage(
            kind='deliver',
            envelope_id='01A',
            received_at_iso='2026-01-01T00:00:00+00:00',
        ),
        BufferedMessage(
            kind='deliver',
            envelope_id='01B',
            received_at_iso='2026-06-01T00:00:00+00:00',
        ),
    ]
    drained = runtime.drain_messages('2026-02-01T00:00:00Z', 10)
    assert len(drained) == 1
    assert drained[0].envelope_id == '01B'
    assert len(runtime._buffer) == 1


class FakeClient:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.relay_http_url = 'http://relay.local'
        self.message_handler = None
        self.receipt_handler = None
        self.connected = False

    def on_message(self, handler: object) -> None:
        self.message_handler = handler

    def on_receipt(self, handler: object) -> None:
        self.receipt_handler = handler

    async def connect(self) -> None:
        self.connected = True

    async def send(self, recipient_did: str, message: str, enc_key: bytes) -> dict[str, object]:
        return {
            'type': 'ack',
            'recipient_did': recipient_did,
            'message': message,
            'key_len': len(enc_key),
        }

    async def get_balance(self) -> int:
        return 123


async def test_runtime_connects_once_buffers_messages_and_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[FakeClient] = []

    def client_factory(**kwargs: object) -> FakeClient:
        client = FakeClient(**kwargs)
        created.append(client)
        return client

    monkeypatch.setattr('plenipo.mcp.runtime.PlenipoClient', client_factory)

    runtime = McpRuntime(
        McpRuntimeConfig(
            did='did:web:test.local',
            auth_secret_b64='AAAA',
            did_document_url='https://test.local/.well-known/did.json',
            relay_url='ws://localhost:4000/agent/websocket',
            enc_secret_b64=base64url.encode(b'\x02' * 32),
        )
    )

    client = await runtime.ensure_connected()
    assert await runtime.ensure_connected() is client
    assert created[0].connected is True

    assert callable(created[0].message_handler)
    created[0].message_handler(
        {
            'envelope_id': '01MSG',
            'sender_did': 'did:web:sender.local',
            'recipient_did': 'did:web:test.local',
            'ciphertext': 'not-valid-base64url',
        }
    )
    assert callable(created[0].receipt_handler)
    created[0].receipt_handler({'envelope_id': '01MSG', 'received_at': 'now'})

    drained = runtime.drain_messages(limit=10)
    assert [entry.kind for entry in drained] == ['deliver', 'receipt']


async def test_runtime_buffers_receipt_billing_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('plenipo.mcp.runtime.PlenipoClient', FakeClient)

    runtime = McpRuntime(
        McpRuntimeConfig(
            did='did:web:test.local',
            auth_secret_b64='AAAA',
            did_document_url='https://test.local/.well-known/did.json',
            relay_url='ws://localhost:4000/agent/websocket',
        )
    )
    client = await runtime.ensure_connected()
    assert client.receipt_handler is not None
    client.receipt_handler(
        {
            'envelope_id': '01MSG',
            'sender_did': 'did:web:sender.local',
            'recipient_did': 'did:web:test.local',
            'received_at': '2026-06-08T00:00:00Z',
            'delivered_at': '2026-06-08T00:00:01Z',
            'ciphertext_bytes': 105,
            'billable_kb': 1,
            'charged_tokens': 1,
            'balance_after': 999,
        }
    )

    receipt = runtime.drain_messages(limit=1)[0]
    assert receipt.kind == 'receipt'
    assert receipt.ciphertext_bytes == 105
    assert receipt.billable_kb == 1
    assert receipt.charged_tokens == 1
    assert receipt.balance_after == 999
    assert receipt.delivered_at == '2026-06-08T00:00:01Z'


async def test_runtime_send_and_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('plenipo.mcp.runtime.PlenipoClient', FakeClient)

    async def fake_resolve(*_args: object, **_kwargs: object) -> bytes:
        return b'k' * 32

    monkeypatch.setattr('plenipo.mcp.runtime.resolve_enc_public_key', fake_resolve)

    runtime = McpRuntime(
        McpRuntimeConfig(
            did='did:web:test.local',
            auth_secret_b64='AAAA',
            did_document_url='https://test.local/.well-known/did.json',
            relay_url='ws://localhost:4000/agent/websocket',
            registry_url='https://registry.local',
        )
    )

    assert await runtime.get_balance() == 123
    ack = await runtime.send('did:web:recipient.local', 'hello')
    assert ack['recipient_did'] == 'did:web:recipient.local'
    assert ack['key_len'] == 32


def test_load_mcp_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from plenipo.mcp.runtime import load_mcp_config_from_env

    monkeypatch.setenv('PLENIPO_DID', 'did:web:env.local')
    monkeypatch.setenv('PLENIPO_AUTH_SECRET_B64', 'AUTH')
    monkeypatch.setenv('PLENIPO_DID_DOCUMENT_URL', 'https://env.local/.well-known/did.json')
    monkeypatch.setenv('PLENIPO_RELAY_URL', 'wss://relay.local/agent/websocket')
    monkeypatch.setenv('PLENIPO_REGISTRY_URL', 'https://registry.local')

    config = load_mcp_config_from_env()
    assert config.did == 'did:web:env.local'
    assert config.registry_url == 'https://registry.local'


def test_load_mcp_config_reads_identity_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from plenipo.identity.store import identity_from_create_result, save_identity
    from plenipo.mcp.runtime import load_mcp_config_from_env

    monkeypatch.delenv('PLENIPO_DID', raising=False)
    monkeypatch.delenv('PLENIPO_AUTH_SECRET_B64', raising=False)
    monkeypatch.delenv('PLENIPO_DID_DOCUMENT_URL', raising=False)
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))

    identity = identity_from_create_result(
        did='did:web:localhost:agents:file',
        auth_secret_b64='AUTH',
        enc_secret_b64='ENC',
        did_document_url='https://localhost/agents/file/did.json',
        document={'id': 'did:web:localhost:agents:file', 'service': []},
        relay_url='ws://localhost:4000/agent/websocket',
        registry_url='http://localhost:4001',
        core_url='http://localhost:4000',
    )
    save_identity(identity)

    config = load_mcp_config_from_env()
    assert config.did == identity.did


def test_load_mcp_config_requires_identity_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from plenipo.mcp.runtime import load_mcp_config_from_env

    monkeypatch.delenv('PLENIPO_DID', raising=False)
    monkeypatch.delenv('PLENIPO_AUTH_SECRET_B64', raising=False)
    monkeypatch.delenv('PLENIPO_DID_PRIVATE_KEY', raising=False)
    monkeypatch.delenv('PLENIPO_DID_DOCUMENT_URL', raising=False)
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))

    with pytest.raises(RuntimeError, match='Missing MCP identity'):
        load_mcp_config_from_env()


def test_runtime_singleton_reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('PLENIPO_DID', 'did:web:singleton.local')
    monkeypatch.setenv('PLENIPO_AUTH_SECRET_B64', 'AUTH')
    monkeypatch.setenv(
        'PLENIPO_DID_DOCUMENT_URL',
        'https://singleton.local/.well-known/did.json',
    )

    reset_mcp_runtime()
    first = get_mcp_runtime()
    assert get_mcp_runtime() is first
    reset_mcp_runtime()
    assert get_mcp_runtime() is not first
    reset_mcp_runtime()
