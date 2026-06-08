"""Identity provisioning tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from plenipo.identity.provision import ensure_identity, identity_to_mcp_config, provision_identity
from plenipo.identity.store import load_identity


async def test_provision_identity_persists_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_register(core_url: str, document: dict[str, object], auth_secret_b64: str):
        calls.append(
            {
                'core_url': core_url,
                'document': document,
                'auth_secret_b64': auth_secret_b64,
            }
        )
        return {'type': 'did_registered', 'did': document['id']}

    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    monkeypatch.setattr('plenipo.identity.provision.register_document', fake_register)

    identity = await provision_identity(
        core_url='http://core.local',
        relay_url='ws://core.local/agent/websocket',
        registry_url='http://registry.local',
    )

    assert identity.did.startswith('did:web:localhost:agents:')
    assert len(calls) == 1
    assert load_identity(tmp_path / 'identity.json') is not None


async def test_ensure_identity_prefers_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    monkeypatch.setenv('PLENIPO_DID', 'did:web:env.local')
    monkeypatch.setenv('PLENIPO_AUTH_SECRET_B64', 'AUTH')
    monkeypatch.setenv('PLENIPO_DID_DOCUMENT_URL', 'https://env.local/.well-known/did.json')

    identity = await ensure_identity()
    assert identity.did == 'did:web:env.local'


async def test_ensure_identity_loads_file_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    monkeypatch.delenv('PLENIPO_DID', raising=False)
    monkeypatch.delenv('PLENIPO_AUTH_SECRET_B64', raising=False)
    monkeypatch.delenv('PLENIPO_DID_DOCUMENT_URL', raising=False)
    monkeypatch.setattr('plenipo.identity.provision.register_document', _noop_register)

    created = await provision_identity()
    monkeypatch.delenv('PLENIPO_DID', raising=False)
    loaded = await ensure_identity()
    assert loaded.did == created.did


def test_identity_to_mcp_config_maps_fields() -> None:
    from plenipo.identity.store import identity_from_create_result

    identity = identity_from_create_result(
        did='did:web:localhost:agents:test',
        auth_secret_b64='AUTH',
        enc_secret_b64='ENC',
        did_document_url='https://localhost/agents/test/did.json',
        document={'id': 'did:web:localhost:agents:test', 'service': []},
        relay_url='ws://localhost:4000/agent/websocket',
        registry_url='http://localhost:4001',
        core_url='http://localhost:4000',
    )
    config = identity_to_mcp_config(identity)
    assert config.did == identity.did
    assert config.auth_secret_b64 == identity.auth_secret_b64


async def _noop_register(*_args: object, **_kwargs: object) -> dict[str, str]:
    return {'type': 'did_registered', 'did': 'did:web:localhost:agents:test'}
