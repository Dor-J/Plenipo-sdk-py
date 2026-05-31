"""Canonical envelope signing input per PROTOCOL §7.2."""

import hashlib

from plenipo.crypto import base64url


def build(envelope: dict[str, str]) -> bytes:
    """Builds UTF-8 signing input bytes for an envelope map."""
    ciphertext = base64url.decode(envelope['ciphertext'])
    digest = hashlib.sha256(ciphertext).digest()
    hash_line = base64url.encode(digest)
    canonical = '\n'.join(
        [
            envelope['v'],
            envelope['envelope_id'],
            envelope['sender_did'],
            envelope['recipient_did'],
            envelope['created_at'],
            hash_line,
        ]
    )
    return canonical.encode('utf-8')
