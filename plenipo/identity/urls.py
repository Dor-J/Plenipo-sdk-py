"""URL helpers for Core-hosted local identities."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlparse


def core_hosted_document_url(core_url: str, did: str) -> str:
    """Returns the Core resolver URL for a Core-hosted DID document."""
    encoded_did = quote(did, safe='')
    return f'{core_url.rstrip("/")}/v1/dids?did={encoded_did}'


def external_did_web_document_url(did: str) -> str:
    """Returns the required HTTPS document URL for an external did:web DID."""
    host, path_segments = _parse_did_web(did)
    if not path_segments:
        return f'https://{host}/.well-known/did.json'
    encoded = '/'.join(quote(segment, safe='') for segment in path_segments)
    return f'https://{host}/{encoded}/did.json'


def validate_production_did_web(did: str, document_url: str) -> None:
    """Validates strict production did:web hosting rules.

    Raises ValueError when the DID is not did:web, the document URL is not HTTPS,
    or the URL does not exactly match the DID-derived document location.
    """
    expected = external_did_web_document_url(did)
    parsed = urlparse(document_url)
    if parsed.scheme != 'https':
        raise ValueError('production DID document URL must use https')
    if document_url != expected:
        raise ValueError(f'DID document URL must be {expected}')


def is_core_hosted_local_did(did: str) -> bool:
    """Returns true for dev-only Core-hosted local DIDs."""
    return did.startswith('did:web:localhost:agents:')


def _parse_did_web(did: str) -> tuple[str, list[str]]:
    prefix = 'did:web:'
    if not did.startswith(prefix) or did == prefix:
        raise ValueError('DID must use did:web')
    parts = did[len(prefix) :].split(':')
    if any(part == '' for part in parts):
        raise ValueError('did:web contains an empty segment')
    host = unquote(parts[0])
    if not host:
        raise ValueError('did:web host is required')
    return host, [unquote(part) for part in parts[1:]]
