"""Tests for x402 payment helpers."""

from plenipo.payments import (
    build_bundle_payment,
    build_relay_payment,
    encode_payment_payload,
    mandate_prepare,
    parse_payment_required,
    purchase_bundle,
)
import base64
import json

import pytest


def test_encode_payment_payload_roundtrip() -> None:
    payload = {
        'payment_id': 'pay_1',
        'agent_did': 'did:web:a.local',
        'purpose': 'bundle_purchase',
        'bundle_id': 'starter',
        'amount_cents': 100,
    }
    encoded = encode_payment_payload(payload)
    decoded = json.loads(base64.urlsafe_b64decode(encoded + '=='))
    assert decoded['bundle_id'] == 'starter'


def test_parse_payment_required() -> None:
    raw = json.dumps({'accepts': [], 'scheme': 'x402-dev'}).encode('utf-8')
    header = base64.urlsafe_b64encode(raw).decode('utf-8').rstrip('=')
    parsed = parse_payment_required(header)
    assert parsed['scheme'] == 'x402-dev'


def test_build_relay_payment() -> None:
    proof = build_relay_payment('did:web:a.local', 1, '01JENV')
    decoded = json.loads(base64.urlsafe_b64decode(proof + '=='))
    assert decoded['purpose'] == 'relay'
    assert decoded['envelope_id'] == '01JENV'


def test_build_bundle_payment() -> None:
    proof = build_bundle_payment('did:web:a.local', 'starter', 100)
    decoded = json.loads(base64.urlsafe_b64decode(proof + '=='))
    assert decoded['bundle_id'] == 'starter'


class Response:
    def __init__(
        self,
        body: dict[str, object],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._body = body
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')

    def json(self) -> dict[str, object]:
        return self._body


class Client:
    responses: list[Response] = []
    posts: list[tuple[str, dict[str, object] | None, dict[str, str] | None]] = []

    async def __aenter__(self) -> 'Client':
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        self.posts.append((url, json, headers))
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def patch_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    Client.responses = []
    Client.posts = []
    monkeypatch.setattr('httpx.AsyncClient', Client)


async def test_purchase_bundle_uses_402_retry_flow() -> None:
    required = encode_payment_payload(
        {
            'accepts': [
                {
                    'bundle_id': 'starter',
                    'amount_cents': 100,
                }
            ],
            'scheme': 'x402-dev',
        }
    )
    Client.responses = [
        Response({}, status_code=402, headers={'payment-required': required}),
        Response({'tokens': 1000, 'balance': 1000}),
    ]

    receipt = await purchase_bundle('https://relay.example/', 'did:web:a.local', 'starter')

    assert receipt == {'tokens': 1000, 'balance': 1000}
    assert len(Client.posts) == 2
    assert Client.posts[1][2] is not None
    assert 'payment-signature' in Client.posts[1][2]


async def test_purchase_bundle_rejects_402_without_requirements() -> None:
    Client.responses = [Response({}, status_code=402)]

    with pytest.raises(ValueError, match='payment-required'):
        await purchase_bundle('https://relay.example', 'did:web:a.local', 'starter')


async def test_mandate_prepare_posts_fields() -> None:
    Client.responses = [Response({'mandate': {'agent_did': 'did:web:a.local'}})]

    result = await mandate_prepare('https://relay.example/', {'agent_did': 'did:web:a.local'})

    assert result == {'mandate': {'agent_did': 'did:web:a.local'}}
    assert Client.posts == [
        ('https://relay.example/operator/prepare', {'agent_did': 'did:web:a.local'}, None)
    ]
