"""Capability declaration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from plenipo.identity.capabilities import declare_capabilities
from plenipo.identity.store import identity_from_create_result, save_identity


async def test_declare_capabilities_updates_identity_and_registers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_register(core_url: str, document: dict[str, object], auth_secret_b64: str):
        calls.append({'core_url': core_url, 'document': document, 'auth_secret_b64': auth_secret_b64})
        return {'type': 'did_registered', 'did': document['id']}

    monkeypatch.setattr('plenipo.identity.sync.register_document', fake_register)

    identity = identity_from_create_result(
        did='did:web:localhost:agents:cap',
        auth_secret_b64='AUTH',
        enc_secret_b64='ENC',
        did_document_url='https://localhost/agents/cap/did.json',
        document={
            'id': 'did:web:localhost:agents:cap',
            'service': [
                {
                    'type': 'PlenipoAgent',
                    'serviceEndpoint': 'ws://localhost:4000/agent/websocket',
                    'capabilities': ['general'],
                }
            ],
        },
        relay_url='ws://localhost:4000/agent/websocket',
        registry_url='http://localhost:4001',
        core_url='http://localhost:4000',
    )
    path = tmp_path / 'identity.json'
    save_identity(identity, path)
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))

    updated = await declare_capabilities(['web_search'], identity=identity)
    assert 'web_search' in updated.capabilities
    assert len(calls) == 1
