"""Relay WebSocket URL builder parity tests."""

from __future__ import annotations

import json
from pathlib import Path

from plenipo.client.relay_connect_url import (
    build_relay_connect_url,
    build_relay_connect_url_vsn_first,
    relay_ws_base_url,
)
from plenipo.identity.urls import core_hosted_document_url

FIXTURES = Path(__file__).resolve().parents[2] / 'test-fixtures' / 'protocol' / 'canonical.json'


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURES.read_text(encoding='utf-8'))


def test_build_relay_connect_url_matches_canonical_fixture() -> None:
    data = _fixture()
    did = str(data['did'])
    relay = str(data['relayWsBase'])
    connect = data['relayConnect']
    assert isinstance(connect, dict)

    url = build_relay_connect_url(
        relay,
        did=did,
        nonce=str(connect['nonce']),
        signature=str(connect['signature']),
        did_document_url=str(data['didDocumentUrl']),
    )
    assert url.endswith(str(connect['expectedQuerySuffix']))
    assert url.startswith(f'{relay_ws_base_url(relay)}?')


def test_did_document_url_uses_query_form() -> None:
    did = 'did:web:localhost:agents:abc123'
    url = core_hosted_document_url('http://127.0.0.1:4000', did)
    assert url == 'http://127.0.0.1:4000/v1/dids?did=did%3Aweb%3Alocalhost%3Aagents%3Aabc123'
    assert '/v1/dids/did:' not in url


def test_vsn_first_and_vsn_last_encode_same_values() -> None:
    data = _fixture()
    kwargs = {
        'did': str(data['did']),
        'nonce': str(data['relayConnect']['nonce']),
        'signature': str(data['relayConnect']['signature']),
        'did_document_url': str(data['didDocumentUrl']),
    }
    last = build_relay_connect_url(str(data['relayWsBase']), **kwargs)
    first = build_relay_connect_url_vsn_first(str(data['relayWsBase']), **kwargs)
    assert 'did%3Aweb%3Alocalhost%3Aagents%3Aabc123' in last
    assert 'did%3Aweb%3Alocalhost%3Aagents%3Aabc123' in first
    assert last.endswith('&vsn=2.0.0')
    assert first.startswith('ws://127.0.0.1:4000/agent/websocket?vsn=2.0.0&')
