"""Resolve DID documents and encryption keys."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any, cast
from urllib.parse import quote, unquote, urlparse

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
    if document.get('id') != did:
        raise ValueError(f'DID document id mismatch for {did}')

    methods = document.get('verificationMethod')
    if not isinstance(methods, list):
        raise ValueError('DID document missing verificationMethod')

    key_agreement = document.get('keyAgreement')
    if not isinstance(key_agreement, list) or not all(isinstance(ref, str) for ref in key_agreement):
        raise ValueError('DID document missing keyAgreement')

    enc_method: dict[str, Any] | None = None
    for method in methods:
        if not isinstance(method, dict):
            continue
        method_id = str(method.get('id', ''))
        method_type = str(method.get('type', ''))
        controller = method.get('controller')
        if (
            method_type == 'X25519KeyAgreementKey2020'
            and method_id in key_agreement
            and (controller is None or controller == did)
        ):
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
    host, *path_segments = did.removeprefix('did:web:').split(':')
    if not host or any(not segment for segment in path_segments):
        return None

    if not path_segments:
        return f'https://{unquote(host)}/.well-known/did.json'

    path = '/'.join(quote(unquote(segment), safe='') for segment in path_segments)
    return f'https://{unquote(host)}/{path}/did.json'


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
            await _validate_document_url_for_did(recipient_document_url, recipient_did)
            res = await client.get(recipient_document_url, follow_redirects=False, timeout=5.0)
            res.raise_for_status()
            return cast(dict[str, Any], res.json())

    try:
        results = await discover_agents(
            query=recipient_did,
            limit=5,
            registry_url=registry_url,
        )
        for row in results:
            if row.get('did') == recipient_did and row.get('document_url'):
                async with httpx.AsyncClient() as client:
                    document_url = str(row['document_url'])
                    await _validate_document_url_for_did(document_url, recipient_did)
                    res = await client.get(document_url, follow_redirects=False, timeout=5.0)
                    res.raise_for_status()
                    return cast(dict[str, Any], res.json())
    except Exception:
        pass

    web_url = _did_web_document_url(recipient_did)
    if web_url:
        try:
            async with httpx.AsyncClient() as client:
                await _validate_document_url_for_did(web_url, recipient_did)
                res = await client.get(web_url, follow_redirects=False, timeout=5.0)
                res.raise_for_status()
                return cast(dict[str, Any], res.json())
        except Exception:
            pass

    async with httpx.AsyncClient() as client:
        res = await client.get(
            f'{relay_http_url}/v1/dids/{quote(recipient_did, safe="")}',
            follow_redirects=False,
            timeout=5.0,
        )
        res.raise_for_status()
        return cast(dict[str, Any], res.json())


async def _validate_document_url_for_did(url: str, did: str) -> None:
    allow_unsafe = os.environ.get('PLENIPO_ALLOW_UNSAFE_DID_FETCH') == 'true'
    expected = _did_web_document_url(did)
    if expected is None:
        raise ValueError(f'Unsupported DID method for direct document fetch: {did}')

    parsed = urlparse(url)
    if not allow_unsafe and parsed.scheme != 'https':
        raise ValueError('DID document URL must use https')

    if not allow_unsafe and url != expected:
        raise ValueError('DID document URL does not match did:web document URL')

    if not allow_unsafe:
        await _assert_public_host(parsed.hostname or '')


async def _assert_public_host(hostname: str) -> None:
    if not hostname:
        raise ValueError('DID document URL missing host')

    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        addresses = list({ipaddress.ip_address(info[4][0]) for info in infos})

    if any(_blocked_address(address) for address in addresses):
        raise ValueError('DID document URL host resolves to a blocked address')


def _blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


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
