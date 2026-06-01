"""DID resolve tests."""

import pytest

from plenipo.did import create_did_document, enc_public_key_from_document
from plenipo.did.resolve import fetch_did_document


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
