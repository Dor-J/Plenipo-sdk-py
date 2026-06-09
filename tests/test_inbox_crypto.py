"""Tests for encrypted local inbox storage."""

from __future__ import annotations

import pytest

from plenipo.runtime.store import RuntimeStore
from plenipo.runtime.inbox_crypto import (
    SidecarStoreKeyError,
    decrypt_plaintext,
    encrypt_plaintext,
    resolve_sidecar_store_key,
    write_sidecar_store_key,
)


def test_encrypt_decrypt_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    key = resolve_sidecar_store_key()
    ciphertext_b64, nonce_b64 = encrypt_plaintext('hello durable inbox', key)
    assert decrypt_plaintext(ciphertext_b64, nonce_b64, key) == 'hello durable inbox'


def test_missing_key_with_inbox_rows_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    store = RuntimeStore()
    key = resolve_sidecar_store_key()
    ciphertext_b64, nonce_b64 = encrypt_plaintext('secret message', key)
    store.insert_inbox_message(
        envelope_id='01TEST',
        sender_did='did:web:sender',
        recipient_did='did:web:recipient',
        received_at='2026-06-09T00:00:00Z',
        plaintext_ciphertext=ciphertext_b64,
        plaintext_nonce=nonce_b64,
        plaintext_alg='nacl-secretbox-v1',
        metadata={},
    )
    key_path = tmp_path / 'sidecar-store.key'
    key_path.unlink()
    with pytest.raises(SidecarStoreKeyError):
        resolve_sidecar_store_key(generate_if_missing=False)


def test_inbox_does_not_store_raw_plaintext(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    store = RuntimeStore()
    key = resolve_sidecar_store_key()
    plaintext = 'super-secret-local-plaintext'
    ciphertext_b64, nonce_b64 = encrypt_plaintext(plaintext, key)
    store.insert_inbox_message(
        envelope_id='01TEST',
        sender_did='did:web:sender',
        recipient_did='did:web:recipient',
        received_at='2026-06-09T00:00:00Z',
        plaintext_ciphertext=ciphertext_b64,
        plaintext_nonce=nonce_b64,
        plaintext_alg='nacl-secretbox-v1',
        metadata={},
    )
    db_bytes = (tmp_path / 'runtime.sqlite').read_bytes()
    assert plaintext.encode('utf-8') not in db_bytes
