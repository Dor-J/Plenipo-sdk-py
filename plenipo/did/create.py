"""DID document generation."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import quote

from plenipo.route_defaults import default_route_service_fields
from nacl.public import PrivateKey
from nacl.signing import SigningKey


@dataclass(frozen=True)
class DidCreateResult:
    """Result of DID creation."""

    did: str
    document_url: str
    document: dict[str, Any]
    auth_secret_b64: str
    enc_secret_b64: str


def _multibase_ed25519(public_key: bytes) -> str:
    import base58

    return 'z' + base58.b58encode(bytes([0xED, 0x01]) + public_key).decode('ascii')


def _multibase_x25519(public_key: bytes) -> str:
    import base58

    return 'z' + base58.b58encode(bytes([0xEC, 0x01]) + public_key).decode('ascii')


def create_did_document(
    domain: str,
    relay_url: str = 'ws://localhost:4000/agent/websocket',
    *,
    path_segments: Sequence[str] | None = None,
) -> DidCreateResult:
    """
    Generates a did:web document and key material for a domain.

    Private keys are returned only to the caller and must not be sent to the relay.
    """
    signing = SigningKey.generate()
    enc = PrivateKey.generate()
    path_segments = list(path_segments or [])
    did = _build_did_web(domain, path_segments)
    document_url = _build_document_url(domain, path_segments)

    document: dict[str, Any] = {
        '@context': [
            'https://www.w3.org/ns/did/v1',
            'https://w3id.org/security/suites/ed25519-2020/v1',
            'https://w3id.org/security/suites/x25519-2020/v1',
        ],
        'id': did,
        'verificationMethod': [
            {
                'id': f'{did}#auth-key',
                'type': 'Ed25519VerificationKey2020',
                'controller': did,
                'publicKeyMultibase': _multibase_ed25519(bytes(signing.verify_key)),
            },
            {
                'id': f'{did}#enc-key',
                'type': 'X25519KeyAgreementKey2020',
                'controller': did,
                'publicKeyMultibase': _multibase_x25519(bytes(enc.public_key)),
            },
        ],
        'authentication': [f'{did}#auth-key'],
        'assertionMethod': [f'{did}#auth-key'],
        'keyAgreement': [f'{did}#enc-key'],
        'service': [
            {
                'id': f'{did}#plenipo',
                'type': 'PlenipoAgent',
                'serviceEndpoint': relay_url,
                'capabilities': ['general', 'mcp'],
                **default_route_service_fields(),
            }
        ],
    }

    return DidCreateResult(
        did=did,
        document_url=document_url,
        document=document,
        auth_secret_b64=base64.urlsafe_b64encode(bytes(signing)).decode('ascii'),
        enc_secret_b64=base64.urlsafe_b64encode(bytes(enc)).decode('ascii'),
    )


def _build_did_web(domain: str, path_segments: Sequence[str]) -> str:
    encoded_path = [quote(segment, safe='') for segment in path_segments]
    return ':'.join(['did:web', domain, *encoded_path])


def _build_document_url(domain: str, path_segments: Sequence[str]) -> str:
    if not path_segments:
        return f'https://{domain}/.well-known/did.json'

    encoded_path = '/'.join(quote(segment, safe='') for segment in path_segments)
    return f'https://{domain}/{encoded_path}/did.json'
