"""Canonical signing payloads for Core DID self-registration."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from nacl.signing import SigningKey

from plenipo.crypto import base64url

REGISTER_TYPE = 'plenipo.did.register'
REGISTER_VERSION = '1.0'


def document_fingerprint(document: dict[str, Any]) -> str:
    """Computes a SHA-256 fingerprint for a DID document."""
    encoded = json.dumps(document, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def build_register_payload(
    *,
    nonce: str,
    did: str,
    document: dict[str, Any],
    timestamp: str | None = None,
) -> dict[str, str]:
    """Builds the canonical registration signing payload."""
    return {
        'type': REGISTER_TYPE,
        'v': REGISTER_VERSION,
        'nonce': nonce,
        'did': did,
        'document_fingerprint': document_fingerprint(document),
        'timestamp': timestamp or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def signing_bytes(payload: dict[str, str]) -> bytes:
    """Returns UTF-8 bytes for the canonical registration payload."""
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sign_register_payload(payload: dict[str, str], auth_secret_b64: str) -> str:
    """Signs a registration payload with the agent auth key."""
    signing = SigningKey(base64url.decode(auth_secret_b64))
    signature = signing.sign(signing_bytes(payload)).signature
    return base64url.encode(signature)
