"""Sync identity tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from plenipo.identity.provision import create_local_identity
from plenipo.identity.sync import sync_identity_with_core, sync_result_to_dict


async def test_sync_identity_core_offline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))

    identity = create_local_identity(core_url='http://127.0.0.1:1')

    _, result = await sync_identity_with_core(identity)
    payload = sync_result_to_dict(result)

    assert result.ok is False
    assert result.core_registered is False
    assert result.registration_pending is True
    assert payload['warnings'] == ['Core unavailable']


async def test_sync_identity_succeeds_with_mock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))

    async def fake_register(core_url: str, document: dict[str, object], auth_secret_b64: str):
        return {
            'type': 'did_registered',
            'did': document['id'],
            'document_fingerprint': 'abc123',
        }

    monkeypatch.setattr('plenipo.identity.sync.register_document', fake_register)

    identity = create_local_identity(core_url='http://core.local')
    synced, result = await sync_identity_with_core(identity)

    assert result.ok is True
    assert synced.core_registered is True
    assert synced.registration_pending is False
    assert synced.document_fingerprint == 'abc123'
