"""Register signing and fingerprint tests."""

from __future__ import annotations

from plenipo.identity.register_signing import (
    build_register_payload,
    document_fingerprint,
    sign_rotation_payload,
    signing_bytes,
)


def test_document_fingerprint_sorts_nested_keys() -> None:
    document = {
        'service': [{'capabilities': ['general'], 'type': 'PlenipoAgent'}],
        'id': 'did:web:localhost:agents:test',
        'verificationMethod': [],
    }
    reordered = {
        'id': document['id'],
        'verificationMethod': [],
        'service': [{'type': 'PlenipoAgent', 'capabilities': ['general']}],
    }
    assert document_fingerprint(document) == document_fingerprint(reordered)


def test_build_register_payload_includes_fingerprint() -> None:
    document = {'id': 'did:web:localhost:agents:test', 'service': []}
    payload = build_register_payload(
        nonce='nonce',
        did='did:web:localhost:agents:test',
        document=document,
        timestamp='2026-06-08T12:00:00Z',
    )
    assert payload['type'] == 'plenipo.did.register'
    assert payload['document_fingerprint'] == document_fingerprint(document)
    assert b'"timestamp":"2026-06-08T12:00:00Z"' in signing_bytes(payload)


def test_sign_rotation_payload_returns_old_and_new_signatures() -> None:
    payload = {
        'type': 'plenipo.did.register',
        'v': '1.0',
        'nonce': 'nonce',
        'did': 'did:web:localhost:agents:test',
        'document_fingerprint': 'abc',
        'timestamp': '2026-06-08T12:00:00Z',
    }
    previous = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    new = 'AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE'

    signatures = sign_rotation_payload(
        payload,
        previous_auth_secret_b64=previous,
        new_auth_secret_b64=new,
    )

    assert set(signatures) == {'previous_signature', 'signature'}
    assert signatures['previous_signature'] != signatures['signature']
