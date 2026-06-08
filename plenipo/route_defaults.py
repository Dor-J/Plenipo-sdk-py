"""Default Route Record constants (no package side effects)."""

from __future__ import annotations

from typing import Any

ENCRYPTION_ALG = 'x25519-xsalsa20poly1305'


def default_route_service_fields() -> dict[str, Any]:
    """Returns default route metadata for the PlenipoAgent service block."""
    return {
        'protocols': ['plenipo.message.v1'],
        'encryption': {
            'alg': ENCRYPTION_ALG,
            'publicKeyRef': '#enc-key',
        },
        'payment': {
            'model': 'per_kb',
            'price_per_kb_tokens': 1,
            'accepted_schemes': ['plenipo-dev-token'],
        },
        'limits': {
            'max_message_kb': 256,
            'offline_queue_ttl_seconds': 86400,
        },
    }
