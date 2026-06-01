"""Canonical signing input tests."""

import hashlib

from plenipo.crypto import base64url
from plenipo.crypto.signing_input import build


def test_build_signing_input_known_vector() -> None:
    ciphertext = b'ciphertext-bytes'
    digest = base64url.encode(hashlib.sha256(ciphertext).digest())
    envelope = {
        'v': '1.0',
        'envelope_id': '01JTEST',
        'sender_did': 'did:web:sender.local',
        'recipient_did': 'did:web:recipient.local',
        'created_at': '2026-06-01T00:00:00Z',
        'ciphertext': base64url.encode(ciphertext),
    }

    assert build(envelope) == (
        '1.0\n'
        '01JTEST\n'
        'did:web:sender.local\n'
        'did:web:recipient.local\n'
        '2026-06-01T00:00:00Z\n'
        f'{digest}'
    ).encode()
