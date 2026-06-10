"""Route Record metadata for agent-first onboarding."""

from __future__ import annotations

import copy
from typing import Any

from plenipo.identity.register_signing import document_fingerprint
from plenipo.identity.store import AgentIdentity, save_identity
from plenipo.identity.sync import sync_identity_with_core

from plenipo.discover.records import RouteRecord, normalize_route_record
from plenipo.route_defaults import ENCRYPTION_ALG, default_route_service_fields

SUPPORTED_PROTOCOLS = frozenset({'plenipo.message.v1'})
SUPPORTED_PAYMENT_MODELS = frozenset({'per_kb'})
SUPPORTED_SCHEMES = frozenset({'plenipo-prepaid-token'})
MAX_PROTOCOLS = 16
MAX_SCHEMES = 8
MAX_PRICE_PER_KB = 1000

__all__ = [
    'RouteRecord',
    'declare_route',
    'normalize_route',
    'normalize_route_record',
    'route_from_document',
    'route_to_did_service_patch',
    'validate_route',
]


def normalize_route(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalizes route metadata with defaults."""
    defaults = default_route_service_fields()
    raw = raw or {}

    payment_in = raw.get('payment') if isinstance(raw.get('payment'), dict) else {}
    limits_in = raw.get('limits') if isinstance(raw.get('limits'), dict) else {}
    encryption_in = raw.get('encryption') if isinstance(raw.get('encryption'), dict) else {}

    protocols = raw.get('protocols')
    if not isinstance(protocols, list) or not protocols:
        protocols = defaults['protocols']

    return {
        'protocols': [str(p) for p in protocols],
        'capabilities': [str(c) for c in raw.get('capabilities', ['general', 'mcp'])],
        'payment': {
            'model': str(payment_in.get('model', defaults['payment']['model'])),
            'price_per_kb_tokens': int(
                payment_in.get('price_per_kb_tokens', defaults['payment']['price_per_kb_tokens'])
            ),
            'accepted_schemes': [
                str(s)
                for s in payment_in.get('accepted_schemes', defaults['payment']['accepted_schemes'])
            ],
        },
        'limits': {
            'max_message_kb': int(
                limits_in.get('max_message_kb', defaults['limits']['max_message_kb'])
            ),
            'offline_queue_ttl_seconds': int(
                limits_in.get(
                    'offline_queue_ttl_seconds',
                    defaults['limits']['offline_queue_ttl_seconds'],
                )
            ),
        },
        'encryption': {
            'alg': str(encryption_in.get('alg', defaults['encryption']['alg'])),
            'publicKeyRef': str(
                encryption_in.get('publicKeyRef')
                or encryption_in.get('public_key_ref')
                or defaults['encryption']['publicKeyRef']
            ),
        },
    }


def validate_route(route: dict[str, Any]) -> None:
    """Validates route metadata; raises ValueError on invalid input."""
    protocols = route.get('protocols', [])
    if not isinstance(protocols, list) or len(protocols) > MAX_PROTOCOLS:
        raise ValueError('invalid protocols')
    if not all(str(p) in SUPPORTED_PROTOCOLS for p in protocols):
        raise ValueError('unsupported protocol')

    payment = route.get('payment', {})
    if payment.get('model') not in SUPPORTED_PAYMENT_MODELS:
        raise ValueError('invalid payment model')
    price = payment.get('price_per_kb_tokens')
    if not isinstance(price, int) or price < 0 or price > MAX_PRICE_PER_KB:
        raise ValueError('invalid price_per_kb_tokens')
    schemes = payment.get('accepted_schemes', [])
    if not isinstance(schemes, list) or len(schemes) > MAX_SCHEMES:
        raise ValueError('invalid accepted_schemes')
    if not all(str(s) in SUPPORTED_SCHEMES for s in schemes):
        raise ValueError('unsupported payment scheme')

    limits = route.get('limits', {})
    max_kb = limits.get('max_message_kb')
    ttl = limits.get('offline_queue_ttl_seconds')
    if not isinstance(max_kb, int) or max_kb < 1 or max_kb > 1024:
        raise ValueError('invalid max_message_kb')
    if not isinstance(ttl, int) or ttl < 1 or ttl > 604_800:
        raise ValueError('invalid offline_queue_ttl_seconds')

    encryption = route.get('encryption', {})
    if encryption.get('alg') != ENCRYPTION_ALG:
        raise ValueError('invalid encryption alg')
    ref = encryption.get('publicKeyRef') or encryption.get('public_key_ref')
    if not isinstance(ref, str) or not ref:
        raise ValueError('invalid encryption public key ref')


def route_to_did_service_patch(
    document: dict[str, Any],
    route: dict[str, Any],
    *,
    relay_url: str | None = None,
) -> dict[str, Any]:
    """Patches the PlenipoAgent service block with route metadata."""
    updated = copy.deepcopy(document)
    services = list(updated.get('service') or [])
    found = False

    for index, service in enumerate(services):
        if service.get('type') == 'PlenipoAgent':
            services[index] = {
                **service,
                'serviceEndpoint': relay_url or service.get('serviceEndpoint'),
                'capabilities': route['capabilities'],
                'protocols': route['protocols'],
                'encryption': route['encryption'],
                'payment': route['payment'],
                'limits': route['limits'],
            }
            found = True
            break

    if not found:
        did = str(updated['id'])
        services.append(
            {
                'id': f'{did}#plenipo',
                'type': 'PlenipoAgent',
                'serviceEndpoint': relay_url,
                'capabilities': route['capabilities'],
                'protocols': route['protocols'],
                'encryption': route['encryption'],
                'payment': route['payment'],
                'limits': route['limits'],
            }
        )

    updated['service'] = services
    return updated


def route_from_document(document: dict[str, Any]) -> dict[str, Any]:
    """Extracts route metadata from a DID document."""
    for service in document.get('service') or []:
        if service.get('type') == 'PlenipoAgent':
            return normalize_route(
                {
                    'protocols': service.get('protocols'),
                    'capabilities': service.get('capabilities'),
                    'encryption': service.get('encryption'),
                    'payment': service.get('payment'),
                    'limits': service.get('limits'),
                }
            )
    return normalize_route({})


async def declare_route(
    *,
    protocols: list[str] | None = None,
    capabilities: list[str] | None = None,
    payment: dict[str, Any] | None = None,
    limits: dict[str, Any] | None = None,
    replace: bool = False,
    identity: AgentIdentity | None = None,
) -> AgentIdentity:
    """Updates route metadata locally and syncs the DID document with Core."""
    from plenipo.identity.provision import ensure_identity

    current = identity or await ensure_identity()
    existing = route_from_document(current.document) if not replace else normalize_route({})

    merged = normalize_route(
        {
            'protocols': protocols or existing['protocols'],
            'capabilities': capabilities or existing['capabilities'],
            'payment': payment or existing['payment'],
            'limits': limits or existing['limits'],
            'encryption': existing['encryption'],
        }
    )
    validate_route(merged)

    document = route_to_did_service_patch(
        current.document,
        merged,
        relay_url=current.relay_url,
    )

    pending = AgentIdentity(
        did=current.did,
        auth_secret_b64=current.auth_secret_b64,
        enc_secret_b64=current.enc_secret_b64,
        did_document_url=current.did_document_url,
        relay_url=current.relay_url,
        registry_url=current.registry_url,
        core_url=current.core_url,
        capabilities=merged['capabilities'],
        created_at=current.created_at,
        document=document,
        did_document_mode=current.did_document_mode,
        core_registered=current.core_registered,
        registration_pending=True,
        last_registration_error=current.last_registration_error,
        document_fingerprint=document_fingerprint(document),
    )
    save_identity(pending)
    synced, _ = await sync_identity_with_core(pending)
    return synced
