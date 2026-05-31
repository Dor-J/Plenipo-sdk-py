"""x402 payment client for Plenipo v0.3."""

from __future__ import annotations

import json
import secrets
import uuid
from typing import Any

import httpx

from plenipo.crypto import base64url

PAYMENT_REQUIRED = 'payment-required'
PAYMENT_SIGNATURE = 'payment-signature'


def encode_payment_payload(payload: dict[str, Any]) -> str:
    """Base64url-encodes a JSON payment payload."""
    return base64url.encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))


def parse_payment_required(header_value: str) -> dict[str, Any]:
    """Parses PAYMENT-REQUIRED header from a 402 response."""
    return json.loads(base64url.decode(header_value).decode('utf-8'))


def build_relay_payment(agent_did: str, cost_tokens: int, envelope_id: str) -> str:
    """Builds a dev relay payment proof for message.send."""
    payload = {
        'payment_id': f'pay_{secrets.token_hex(8)}',
        'agent_did': agent_did,
        'purpose': 'relay',
        'envelope_id': envelope_id,
        'cost_tokens': cost_tokens,
    }
    return encode_payment_payload(payload)


def build_bundle_payment(agent_did: str, bundle_id: str, amount_cents: int) -> str:
    """Builds a dev bundle purchase payment proof."""
    payload = {
        'payment_id': f'pay_{uuid.uuid4().hex[:16]}',
        'agent_did': agent_did,
        'purpose': 'bundle_purchase',
        'bundle_id': bundle_id,
        'amount_cents': amount_cents,
    }
    return encode_payment_payload(payload)


async def purchase_bundle(
    relay_http_url: str,
    agent_did: str,
    bundle_id: str,
) -> dict[str, Any]:
    """Purchases a token bundle via HTTP 402 retry flow."""
    url = f'{relay_http_url.rstrip("/")}/v1/bundles/purchase'
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json={'agent_did': agent_did, 'bundle_id': bundle_id})
        if res.status_code == 402:
            required = res.headers.get(PAYMENT_REQUIRED)
            if not required:
                raise ValueError('402 without payment-required header')
            accept = parse_payment_required(required)['accepts'][0]
            sig = build_bundle_payment(
                agent_did,
                accept.get('bundle_id', bundle_id),
                accept['amount_cents'],
            )
            res = await client.post(
                url,
                json={'agent_did': agent_did, 'bundle_id': bundle_id},
                headers={PAYMENT_SIGNATURE: sig},
            )
        res.raise_for_status()
        return res.json()


async def mandate_prepare(
    relay_http_url: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Returns unsigned mandate JSON and signing input for operator signing."""
    async with httpx.AsyncClient() as client:
        res = await client.post(f'{relay_http_url.rstrip("/")}/operator/prepare', json=fields)
        res.raise_for_status()
        return res.json()
