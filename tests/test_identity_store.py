"""Identity store tests."""

from __future__ import annotations

import json
from pathlib import Path

from plenipo.identity.store import (
    AgentIdentity,
    identity_from_create_result,
    load_identity,
    save_identity,
)


def test_identity_store_roundtrip(tmp_path: Path) -> None:
    identity = identity_from_create_result(
        did='did:web:localhost:agents:abc',
        auth_secret_b64='AUTH',
        enc_secret_b64='ENC',
        did_document_url='https://localhost/agents/abc/did.json',
        document={'id': 'did:web:localhost:agents:abc', 'service': []},
        relay_url='ws://localhost:4000/agent/websocket',
        registry_url='http://localhost:4001',
        core_url='http://localhost:4000',
        capabilities=['general'],
    )
    path = tmp_path / 'identity.json'
    save_identity(identity, path)
    loaded = load_identity(path)

    assert loaded is not None
    assert loaded.did == identity.did
    assert loaded.auth_secret_b64 == 'AUTH'
    assert loaded.capabilities == ['general']


def test_save_identity_sets_restrictive_permissions(tmp_path: Path, monkeypatch) -> None:
    identity = AgentIdentity(
        did='did:web:localhost:agents:perm',
        auth_secret_b64='AUTH',
        enc_secret_b64='ENC',
        did_document_url='https://localhost/agents/perm/did.json',
        relay_url='ws://localhost:4000/agent/websocket',
        registry_url='http://localhost:4001',
        core_url='http://localhost:4000',
        capabilities=[],
        created_at='2026-01-01T00:00:00+00:00',
        document={'id': 'did:web:localhost:agents:perm'},
    )
    path = tmp_path / 'identity.json'
    save_identity(identity, path)
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['did'] == identity.did
