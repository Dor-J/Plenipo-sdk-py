"""Route Record tests."""

from __future__ import annotations

import pytest

from plenipo.identity.route import (
    declare_route,
    normalize_route,
    normalize_route_record,
    route_from_document,
    route_to_did_service_patch,
    validate_route,
)


def test_normalize_route_defaults() -> None:
    route = normalize_route({})
    assert route['protocols'] == ['plenipo.message.v1']
    assert route['payment']['model'] == 'per_kb'
    assert route['encryption']['publicKeyRef'] == '#enc-key'


def test_validate_route_rejects_bad_protocol() -> None:
    route = normalize_route({'protocols': ['bad.protocol']})
    with pytest.raises(ValueError, match='protocol'):
        validate_route(route)


def test_route_to_did_service_patch() -> None:
    document = {
        'id': 'did:web:localhost:agents:abc',
        'service': [
            {
                'id': 'did:web:localhost:agents:abc#plenipo',
                'type': 'PlenipoAgent',
                'serviceEndpoint': 'ws://localhost:4000/agent/websocket',
                'capabilities': ['general'],
            }
        ],
    }
    route = normalize_route({'capabilities': ['general', 'mcp']})
    updated = route_to_did_service_patch(document, route, relay_url='ws://localhost:4000/agent/websocket')
    service = updated['service'][0]
    assert service['protocols'] == ['plenipo.message.v1']
    assert service['payment']['price_per_kb_tokens'] == 1


def test_normalize_route_record_from_registry() -> None:
    record = normalize_route_record(
        {
            'did': 'did:web:localhost:agents:abc',
            'document_url': 'http://localhost:4000/v1/dids/abc',
            'capabilities': ['mcp'],
            'encryption': {'alg': 'x25519-xsalsa20poly1305', 'public_key_ref': '#enc-key'},
            'payment': {
                'model': 'per_kb',
                'price_per_kb_tokens': 1,
                'accepted_schemes': ['plenipo-prepaid-token'],
            },
            'limits': {'max_message_kb': 256, 'offline_queue_ttl_seconds': 86400},
        }
    )
    assert record['did'].startswith('did:web:')
    assert record['payment']['accepted_schemes'] == ['plenipo-prepaid-token']


async def test_declare_route_updates_document(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from plenipo.identity.provision import create_local_identity

    async def fake_sync(identity, *, timeout=10.0):
        return identity, type('R', (), {'ok': True, 'warnings': []})()

    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    monkeypatch.setattr('plenipo.identity.route.sync_identity_with_core', fake_sync)

    identity = create_local_identity()
    updated = await declare_route(
        protocols=['plenipo.message.v1'],
        capabilities=['general', 'mcp'],
        identity=identity,
    )
    route = route_from_document(updated.document)
    assert route['capabilities'] == ['general', 'mcp']
    assert updated.document_fingerprint
