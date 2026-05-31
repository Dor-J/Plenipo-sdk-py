"""Resolve DID documents and encryption keys."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from plenipo.discover import discover_agents


def _decode_multibase_x25519(multibase: str) -> bytes:
    import base58

    if not multibase.startswith('z'):
        raise ValueError('Unsupported publicKeyMultibase encoding')
    raw = base58.b58decode(multibase[1:])
    if len(raw) != 34 or raw[0] != 0xEC or raw[1] != 0x01:
        raise ValueError('Invalid X25519 multibase key')
    return raw[2:]


def enc_public_key_from_document(document: dict[str, Any], did: str) -> bytes:
    """Extracts X25519 public key bytes from a DID document."""
    methods = document.get('verificationMethod')
    if not isinstance(methods, list):
        raise ValueError('DID document missing verificationMethod')

    enc_method = None
    for method in methods:
        if not isinstance(method, dict):
            continue
        method_id = str(method.get('id', ''))
        method_type = str(method.get('type', ''))
        if (
            method_type == 'X25519KeyAgreementKey2020'
            or method_id.endswith('#enc-key')
            or method_id in (document.get('keyAgreement') or [])
        ):
            enc_method = method
            break

    if enc_method is None:
        for method in methods:
            if isinstance(method, dict) and 'X25519' in str(method.get('type', '')):
                enc_method = method
                break

    if enc_method is None:
        raise ValueError(f'No encryption key in DID document for {did}')

    multibase = str(enc_method.get('publicKeyMultibase', ''))
    if not multibase:
        raise ValueError('Encryption verification method missing publicKeyMultibase')
    return _decode_multibase_x25519(multibase)


def _did_web_document_url(did: str) -> str | None:
    if not did.startswith('did:web:'):
        return None
    path = did.removeprefix('did:web:').replace(':', '/')
    host = path.split('/')[0]
    rest = f'/{"/".join(path.split("/")[1:])}' if '/' in path else ''
    return f'https://{host}{rest}/.well-known/did.json'


async def fetch_did_document(
    recipient_did: str,
    *,
    recipient_document_url: str | None = None,
    registry_url: str | None = None,
    relay_http_url: str = 'http://localhost:4000',
) -> dict[str, Any]:
    """Fetches a DID document using registry, did:web, or relay resolver."""
    if recipient_document_url:
        async with httpx.AsyncClient() as client:
            res = await client.get(recipient_document_url)
            res.raise_for_status()
            return res.json()

    try:
        results = await discover_agents(
            query=recipient_did,
            limit=5,
            registry_url=registry_url,
        )
        for row in results:
            if row.get('did') == recipient_did and row.get('document_url'):
                async with httpx.AsyncClient() as client:
                    res = await client.get(row['document_url'])
                    res.raise_for_status()
                    return res.json()
    except Exception:
        pass

    web_url = _did_web_document_url(recipient_did)
    if web_url:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(web_url)
                res.raise_for_status()
                return res.json()
        except Exception:
            pass

    async with httpx.AsyncClient() as client:
        res = await client.get(f'{relay_http_url}/v1/dids/{quote(recipient_did, safe="")}')
        res.raise_for_status()
        return res.json()


async def resolve_enc_public_key(
    recipient_did: str,
    *,
    recipient_document_url: str | None = None,
    registry_url: str | None = None,
    relay_http_url: str = 'http://localhost:4000',
) -> bytes:
    """Resolves recipient X25519 encryption public key."""
    document = await fetch_did_document(
        recipient_did,
        recipient_document_url=recipient_document_url,
        registry_url=registry_url,
        relay_http_url=relay_http_url,
    )
    return enc_public_key_from_document(document, recipient_did)
