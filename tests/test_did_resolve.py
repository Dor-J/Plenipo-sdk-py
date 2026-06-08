"""DID resolve tests."""

import pytest

from plenipo.did import create_did_document, enc_public_key_from_document
from typing import Any

from plenipo.did.resolve import fetch_did_document, resolve_enc_public_key


def test_enc_public_key_from_document() -> None:
    result = create_did_document('agent.example.com')
    pub = enc_public_key_from_document(result.document, result.did)
    assert len(pub) == 32


def test_rejects_did_document_id_mismatch() -> None:
    result = create_did_document('agent.example.com')
    poisoned = {**result.document, 'id': 'did:web:attacker.example.com'}

    with pytest.raises(ValueError, match='id mismatch'):
        enc_public_key_from_document(poisoned, result.did)


def test_rejects_x25519_key_not_referenced_by_key_agreement() -> None:
    result = create_did_document('agent.example.com')
    poisoned = {**result.document, 'keyAgreement': []}

    with pytest.raises(ValueError, match='keyAgreement|No encryption key'):
        enc_public_key_from_document(poisoned, result.did)


async def test_rejects_unsafe_caller_supplied_document_url() -> None:
    with pytest.raises(ValueError, match='https|does not match'):
        await fetch_did_document(
            'did:web:agent.example.com',
            recipient_document_url='http://127.0.0.1/.well-known/did.json',
        )


def test_rejects_missing_verification_methods() -> None:
    with pytest.raises(ValueError, match='verificationMethod'):
        enc_public_key_from_document({'id': 'did:web:agent.example.com'}, 'did:web:agent.example.com')


def test_rejects_unsupported_x25519_multibase() -> None:
    result = create_did_document('agent.example.com')
    poisoned = {
        **result.document,
        'verificationMethod': [
            {
                **result.document['verificationMethod'][1],
                'publicKeyMultibase': 'not-base58btc',
            }
        ],
        'keyAgreement': [result.document['keyAgreement'][0]],
    }

    with pytest.raises(ValueError, match='Unsupported publicKeyMultibase'):
        enc_public_key_from_document(poisoned, result.did)


def test_rejects_invalid_x25519_multibase_length() -> None:
    result = create_did_document('agent.example.com')
    methods = result.document['verificationMethod']
    poisoned = {
        **result.document,
        'verificationMethod': [
            {
                **methods[1],
                'publicKeyMultibase': 'z111',
            }
        ],
    }

    with pytest.raises(ValueError, match='Invalid X25519 multibase key'):
        enc_public_key_from_document(poisoned, result.did)


def test_rejects_missing_x25519_multibase() -> None:
    result = create_did_document('agent.example.com')
    methods = result.document['verificationMethod']
    poisoned = {
        **result.document,
        'verificationMethod': [
            {
                **methods[1],
                'publicKeyMultibase': '',
            }
        ],
    }

    with pytest.raises(ValueError, match='publicKeyMultibase'):
        enc_public_key_from_document(poisoned, result.did)


def test_skips_non_dict_and_wrong_controller_methods() -> None:
    result = create_did_document('agent.example.com')
    methods = result.document['verificationMethod']
    poisoned = {
        **result.document,
        'verificationMethod': [
            'not-a-method',
            {
                **methods[1],
                'controller': 'did:web:attacker.example.com',
            },
        ],
    }

    with pytest.raises(ValueError, match='No encryption key'):
        enc_public_key_from_document(poisoned, result.did)


class Response:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')

    def json(self) -> dict[str, Any]:
        return self._body


class Client:
    responses: list[Response] = []
    calls: list[str] = []

    async def __aenter__(self) -> 'Client':
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get(self, url: str, **_kwargs: object) -> Response:
        self.calls.append(url)
        return self.responses.pop(0)


async def test_rejects_blocked_document_host() -> None:
    with pytest.raises(ValueError, match='blocked address'):
        await fetch_did_document(
            'did:web:127.0.0.1',
            recipient_document_url='https://127.0.0.1/.well-known/did.json',
        )


async def test_fetch_uses_registry_result(monkeypatch: pytest.MonkeyPatch) -> None:
    result = create_did_document('agent.example.com')
    monkeypatch.setenv('PLENIPO_ALLOW_UNSAFE_DID_FETCH', 'true')
    monkeypatch.setattr('httpx.AsyncClient', Client)
    Client.responses = [Response(result.document)]
    Client.calls = []

    async def fake_discover(**_kwargs: object) -> list[dict[str, object]]:
        return [{'did': result.did, 'document_url': 'https://agent.example.com/.well-known/did.json'}]

    monkeypatch.setattr('plenipo.discover.discover_agents', fake_discover)

    assert await fetch_did_document(result.did, registry_url='https://registry.example') == result.document
    assert Client.calls == ['https://agent.example.com/.well-known/did.json']


async def test_fetch_uses_did_web_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    result = create_did_document('agent.example.com')
    monkeypatch.setenv('PLENIPO_ALLOW_UNSAFE_DID_FETCH', 'true')
    monkeypatch.setattr('httpx.AsyncClient', Client)
    Client.responses = [Response(result.document)]
    Client.calls = []

    async def fake_discover(**_kwargs: object) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr('plenipo.discover.discover_agents', fake_discover)

    assert await fetch_did_document(result.did) == result.document
    assert Client.calls == ['https://agent.example.com/.well-known/did.json']


async def test_fetch_uses_path_based_did_web_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    result = create_did_document('agents.example.com', path_segments=['local', 'python-a'])
    monkeypatch.setenv('PLENIPO_ALLOW_UNSAFE_DID_FETCH', 'true')
    monkeypatch.setattr('httpx.AsyncClient', Client)
    Client.responses = [Response(result.document)]
    Client.calls = []

    async def fake_discover(**_kwargs: object) -> list[dict[str, object]]:
        return []

    monkeypatch.setattr('plenipo.discover.discover_agents', fake_discover)

    assert await fetch_did_document(result.did) == result.document
    assert Client.calls == ['https://agents.example.com/local/python-a/did.json']


async def test_fetch_falls_back_to_relay_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    did = 'did:web:agent.example.com'
    monkeypatch.setenv('PLENIPO_ALLOW_UNSAFE_DID_FETCH', 'true')
    monkeypatch.setattr('httpx.AsyncClient', Client)
    Client.responses = [Response({}, status_code=404), Response({'id': did})]
    Client.calls = []

    async def fake_discover(**_kwargs: object) -> list[dict[str, object]]:
        raise RuntimeError('registry down')

    monkeypatch.setattr('plenipo.discover.discover_agents', fake_discover)

    assert await fetch_did_document(did, relay_http_url='https://relay.example') == {'id': did}
    assert Client.calls == [
        'https://agent.example.com/.well-known/did.json',
        'https://relay.example/v1/dids?did=did%3Aweb%3Aagent.example.com',
    ]


async def test_resolve_enc_public_key_from_direct_document(monkeypatch: pytest.MonkeyPatch) -> None:
    result = create_did_document('agent.example.com')
    monkeypatch.setenv('PLENIPO_ALLOW_UNSAFE_DID_FETCH', 'true')
    monkeypatch.setattr('httpx.AsyncClient', Client)
    Client.responses = [Response(result.document)]

    key = await resolve_enc_public_key(
        result.did,
        recipient_document_url='https://agent.example.com/.well-known/did.json',
    )

    assert len(key) == 32


async def test_rejects_direct_fetch_for_unsupported_did_method() -> None:
    with pytest.raises(ValueError, match='Unsupported DID method'):
        await fetch_did_document(
            'did:key:z6Mk',
            recipient_document_url='https://agent.example.com/.well-known/did.json',
        )


async def test_direct_fetch_propagates_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            raise RuntimeError('HTTP 404')

        def json(self) -> dict[str, object]:
            return {}

    class Client:
        async def __aenter__(self) -> 'Client':
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setenv('PLENIPO_ALLOW_UNSAFE_DID_FETCH', 'true')
    monkeypatch.setattr('httpx.AsyncClient', Client)

    with pytest.raises(RuntimeError, match='HTTP 404'):
        await fetch_did_document(
            'did:web:agent.example.com',
            recipient_document_url='https://agent.example.com/.well-known/did.json',
        )


async def test_direct_fetch_propagates_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            raise ValueError('bad json')

    class Client:
        async def __aenter__(self) -> 'Client':
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

        async def get(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setenv('PLENIPO_ALLOW_UNSAFE_DID_FETCH', 'true')
    monkeypatch.setattr('httpx.AsyncClient', Client)

    with pytest.raises(ValueError, match='bad json'):
        await fetch_did_document(
            'did:web:agent.example.com',
            recipient_document_url='https://agent.example.com/.well-known/did.json',
        )
