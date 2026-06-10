"""Core self-registration client."""

from __future__ import annotations

from typing import Any

import httpx

from plenipo.identity.register_signing import (
    build_register_payload,
    sign_register_payload,
)


async def fetch_auth_challenge(core_url: str, did: str) -> str:
    """Requests a relay auth challenge nonce for proof-of-possession."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f'{core_url.rstrip("/")}/auth/challenge',
            json={'did': did},
            timeout=10.0,
        )
        response.raise_for_status()
        body = response.json()
        nonce = body.get('nonce')
        if not isinstance(nonce, str):
            raise ValueError('challenge response missing nonce')
        return nonce


async def register_document(
    core_url: str,
    document: dict[str, Any],
    auth_secret_b64: str,
) -> dict[str, Any]:
    """Registers or updates a DID document with Core-hosted storage."""
    did = str(document['id'])
    nonce = await fetch_auth_challenge(core_url, did)
    payload = build_register_payload(nonce=nonce, did=did, document=document)
    signature = sign_register_payload(payload, auth_secret_b64)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f'{core_url.rstrip("/")}/v1/dids',
            json={
                'document': document,
                'nonce': nonce,
                'timestamp': payload['timestamp'],
                'signature': signature,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return dict(response.json())
