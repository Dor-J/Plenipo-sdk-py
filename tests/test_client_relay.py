"""Relay client unit tests with fake HTTP and WebSocket transports."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from nacl.public import PrivateKey

from plenipo.client.relay import PlenipoClient
from plenipo.crypto import base64url


AUTH_SECRET = base64url.encode(b'\x01' * 32)
NONCE = base64url.encode(b'nonce')


class FakeHttpResponse:
    def json(self) -> dict[str, str]:
        return {'nonce': NONCE}


class FakeHttpClient:
    async def __aenter__(self) -> 'FakeHttpClient':
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, Any]) -> FakeHttpResponse:
        assert url == 'http://localhost:4000/auth/challenge'
        assert json == {'did': 'did:web:agent.local'}
        return FakeHttpResponse()


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[list[Any]] = []
        self.messages = [
            json.dumps([None, None, 'relay:inbox', 'phx_reply', {'status': 'ok'}]),
        ]

    async def send(self, data: str) -> None:
        self.sent.append(json.loads(data))

    def __aiter__(self) -> 'FakeWebSocket':
        return self

    async def __anext__(self) -> str:
        if self.messages:
            return self.messages.pop(0)
        raise StopAsyncIteration


@pytest.fixture
def client() -> PlenipoClient:
    return PlenipoClient(
        did='did:web:agent.local',
        auth_secret_b64=AUTH_SECRET,
        did_document_url='https://agent.local/.well-known/did.json',
        relay_url='ws://localhost:4000/agent/websocket',
    )


async def test_list_receipts_requests_receipt_list(
    monkeypatch: pytest.MonkeyPatch,
    client: PlenipoClient,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_request(ref: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.update({'ref': ref, 'event': event, 'payload': payload})
        return {
            'type': 'receipt.list.result',
            'receipts': [{'envelope_id': '01J', 'charged_tokens': 1}],
            'next_cursor': 'cursor-next',
        }

    monkeypatch.setattr(client, '_request_reply', fake_request)
    result = await client.list_receipts(since='2026-06-08T20:56:00Z', limit=5)
    assert result['receipts'] == [{'envelope_id': '01J', 'charged_tokens': 1}]
    assert result['next_cursor'] == 'cursor-next'
    assert captured['event'] == 'receipt.list'
    assert captured['payload'] == {'since': '2026-06-08T20:56:00Z', 'limit': 5}


async def test_list_receipts_prefers_cursor_over_since(
    monkeypatch: pytest.MonkeyPatch,
    client: PlenipoClient,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_request(ref: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.update({'payload': payload})
        return {'type': 'receipt.list.result', 'receipts': [], 'next_cursor': None}

    monkeypatch.setattr(client, '_request_reply', fake_request)
    await client.list_receipts(since='2026-06-08T20:56:00Z', cursor='cursor-1', limit=5)
    assert captured['payload'] == {'cursor': 'cursor-1', 'limit': 5}


async def test_connect_authenticates_and_joins(monkeypatch: pytest.MonkeyPatch, client: PlenipoClient) -> None:
    ws = FakeWebSocket()
    monkeypatch.setattr('httpx.AsyncClient', FakeHttpClient)

    async def fake_connect(url: str) -> FakeWebSocket:
        assert 'did=did%3Aweb%3Aagent.local' in url
        assert 'nonce=' in url
        assert 'signature=' in url
        return ws

    monkeypatch.setattr('websockets.connect', fake_connect)

    await client.connect()
    await asyncio.sleep(0)

    assert ws.sent == [['1', None, 'relay:inbox', 'phx_join', {}]]


async def test_send_builds_signed_envelope_and_payment(
    monkeypatch: pytest.MonkeyPatch,
    client: PlenipoClient,
) -> None:
    recipient_private = PrivateKey.generate()
    captured: dict[str, Any] = {}

    async def fake_request(ref: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.update({'ref': ref, 'event': event, 'payload': payload})
        return {'type': 'ack', 'v': '1.0', 'envelope_id': '01J', 'status': 'queued'}

    monkeypatch.setattr(client, '_request_reply', fake_request)

    ack = await client.send(
        'did:web:recipient.local',
        'hello',
        bytes(recipient_private.public_key),
    )

    assert ack['status'] == 'queued'
    assert captured['event'] == 'message.send'
    envelope = captured['payload']['envelope']
    assert envelope['sender_did'] == 'did:web:agent.local'
    assert envelope['recipient_did'] == 'did:web:recipient.local'
    assert envelope['signature']
    assert captured['payload']['payment']['x402']


async def test_send_accepts_caller_envelope_id(
    monkeypatch: pytest.MonkeyPatch,
    client: PlenipoClient,
) -> None:
    recipient_private = PrivateKey.generate()
    captured: dict[str, Any] = {}

    async def fake_request(ref: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.update({'payload': payload})
        return {'type': 'ack', 'v': '1.0', 'envelope_id': '01CUSTOM', 'status': 'queued'}

    monkeypatch.setattr(client, '_request_reply', fake_request)

    ack = await client.send(
        'did:web:recipient.local',
        'hello',
        bytes(recipient_private.public_key),
        envelope_id='01CUSTOM',
    )

    assert ack['envelope_id'] == '01CUSTOM'
    assert captured['payload']['envelope']['envelope_id'] == '01CUSTOM'


async def test_channel_helpers_send_expected_events(
    monkeypatch: pytest.MonkeyPatch,
    client: PlenipoClient,
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    async def fake_request(_ref: str, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        events.append((event, payload))
        if event == 'balance.get':
            return {'balance': 42}
        return {'ok': True}

    monkeypatch.setattr(client, '_request_reply', fake_request)

    assert await client.send_receipt('01JENV') == {'ok': True}
    assert await client.get_delivery_status('01JENV') == {'ok': True}
    assert await client.get_balance() == 42
    assert events == [
        ('message.receipt', {'envelope_id': '01JENV'}),
        ('delivery.get', {'envelope_id': '01JENV'}),
        ('balance.get', {}),
    ]


async def test_handle_phoenix_resolves_replies_and_push_handlers(
    monkeypatch: pytest.MonkeyPatch,
    client: PlenipoClient,
) -> None:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[Any] = loop.create_future()
    client._pending['2'] = future
    joined = asyncio.Event()

    await client._handle_phoenix(
        ['1', '2', 'relay:inbox', 'phx_reply', {'status': 'ok', 'response': {'balance': 7}}],
        joined,
    )
    assert future.result() == {'balance': 7}

    errors: asyncio.Future[Any] = loop.create_future()
    client._pending['3'] = errors
    await client._handle_phoenix(
        ['1', '3', 'relay:inbox', 'phx_reply', {'status': 'error', 'response': {'code': 'bad'}}],
        joined,
    )
    with pytest.raises(RuntimeError):
        errors.result()

    delivered: list[dict[str, Any]] = []
    receipts: list[str] = []
    client.on_message(lambda payload: delivered.append(payload))

    async def fake_receipt(envelope_id: str) -> dict[str, Any]:
        receipts.append(envelope_id)
        return {'ok': True}

    monkeypatch.setattr(client, 'send_receipt', fake_receipt)
    await client._handle_phoenix(
        ['1', None, 'relay:inbox', 'message.deliver', {'envelope_id': '01JDELIVER'}],
        joined,
    )

    receipt_payloads: list[dict[str, Any]] = []
    client.on_receipt(lambda payload: receipt_payloads.append(payload))
    await client._handle_phoenix(
        ['1', None, 'relay:inbox', 'message.receipt', {'envelope_id': '01JDELIVER'}],
        joined,
    )

    assert delivered == [{'envelope_id': '01JDELIVER'}]
    assert receipts == ['01JDELIVER']
    assert receipt_payloads == [{'envelope_id': '01JDELIVER'}]
