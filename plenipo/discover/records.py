"""Registry Route Record normalization (no identity imports)."""

from __future__ import annotations

from typing import Any, TypedDict

from plenipo.route_defaults import ENCRYPTION_ALG, default_route_service_fields


class RouteRecord(TypedDict, total=False):
    """Public Route Record shape returned by discovery."""

    did: str
    document_url: str
    service_endpoint: str | None
    protocols: list[str]
    capabilities: list[str]
    encryption: dict[str, str]
    payment: dict[str, Any]
    limits: dict[str, int]
    status: dict[str, Any]
    document_fingerprint: str | None
    last_indexed_at: str | None


def normalize_route_record(raw: dict[str, Any]) -> RouteRecord:
    """Normalizes a Registry search result into a Route Record."""
    defaults = default_route_service_fields()
    payment = raw.get('payment') if isinstance(raw.get('payment'), dict) else defaults['payment']
    limits = raw.get('limits') if isinstance(raw.get('limits'), dict) else defaults['limits']
    encryption = raw.get('encryption') if isinstance(raw.get('encryption'), dict) else defaults['encryption']

    enc_ref = encryption.get('public_key_ref') or encryption.get('publicKeyRef') or '#enc-key'

    return {
        'did': str(raw.get('did', '')),
        'document_url': str(raw.get('document_url', '')),
        'service_endpoint': raw.get('service_endpoint'),
        'protocols': list(raw.get('protocols') or defaults['protocols']),
        'capabilities': list(raw.get('capabilities') or []),
        'encryption': {
            'alg': str(encryption.get('alg', ENCRYPTION_ALG)),
            'public_key_ref': str(enc_ref),
        },
        'payment': {
            'model': str(payment.get('model', 'per_kb')),
            'price_per_kb_tokens': int(payment.get('price_per_kb_tokens', 1)),
            'accepted_schemes': list(
                payment.get('accepted_schemes') or ['plenipo-dev-token']
            ),
        },
        'limits': {
            'max_message_kb': int(limits.get('max_message_kb', 256)),
            'offline_queue_ttl_seconds': int(limits.get('offline_queue_ttl_seconds', 86400)),
        },
        'status': raw.get('status')
        if isinstance(raw.get('status'), dict)
        else {'last_seen_at': None, 'delivery_success_rate': None},
        'document_fingerprint': raw.get('document_fingerprint'),
        'last_indexed_at': raw.get('last_indexed_at'),
    }
