"""x402 payment client for Plenipo v0.3."""

from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Any, cast

import httpx

from plenipo.crypto import base64url

PAYMENT_REQUIRED = 'payment-required'
PAYMENT_SIGNATURE = 'payment-signature'


def encode_payment_payload(payload: dict[str, Any]) -> str:
    """Base64url-encodes a JSON payment payload."""
    return base64url.encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))


def parse_payment_required(header_value: str) -> dict[str, Any]:
    """Parses PAYMENT-REQUIRED header from a 402 response."""
    return cast(dict[str, Any], json.loads(base64url.decode(header_value).decode('utf-8')))


def build_relay_payment(agent_did: str, cost_tokens: int, envelope_id: str) -> str:
    """Builds a prepaid relay payment proof for message.send."""
    payload = {
        'scheme': 'plenipo-prepaid-token',
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
        'scheme': 'x402-dev',
        'payment_id': f'pay_{uuid.uuid4().hex[:16]}',
        'agent_did': agent_did,
        'purpose': 'bundle_purchase',
        'bundle_id': bundle_id,
        'amount_cents': amount_cents,
    }
    return encode_payment_payload(payload)


def build_production_bundle_payment(
    *,
    agent_did: str,
    bundle_id: str,
    amount_cents: int,
    network: str,
    pay_to: str,
    payer: str,
    signature: str,
    asset: str = 'USDC',
    expires_at: str | None = None,
    payment_id: str | None = None,
) -> str:
    """Builds a production x402 bundle purchase payload."""
    from datetime import UTC, datetime, timedelta

    payload = {
        'scheme': 'x402',
        'payment_id': payment_id or f'pay_{uuid.uuid4().hex[:16]}',
        'agent_did': agent_did,
        'purpose': 'bundle_purchase',
        'bundle_id': bundle_id,
        'amount_cents': amount_cents,
        'network': network,
        'asset': asset,
        'pay_to': pay_to,
        'payer': payer,
        'expires_at': expires_at
        or (datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'signature': signature,
    }
    return encode_payment_payload(payload)


def detect_wallet_capabilities(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Detects configured wallet providers without initializing them."""
    env = env if env is not None else dict(os.environ)
    providers: list[str] = []
    raw_x402 = bool(env.get('X402_PRIVATE_KEY') or env.get('PLENIPO_X402_PRIVATE_KEY'))
    coinbase_cdp = bool(env.get('CDP_API_KEY_ID') or env.get('CDP_API_KEY_SECRET'))
    crossmint = bool(env.get('CROSSMINT_API_KEY'))

    if raw_x402:
        providers.append('raw-x402')
    if coinbase_cdp:
        providers.append('coinbase-cdp')
    if crossmint:
        providers.append('crossmint')

    return {
        'available': bool(providers),
        'providers': providers,
        'raw_x402_private_key': raw_x402,
        'coinbase_cdp': coinbase_cdp,
        'crossmint': crossmint,
    }


def should_auto_topup(
    balance_tokens: int,
    *,
    enabled: bool,
    threshold_tokens: int,
    max_amount_cents: int,
) -> bool:
    """Returns whether an explicit auto-topup policy allows a topup."""
    return enabled and max_amount_cents > 0 and balance_tokens <= threshold_tokens


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
        return cast(dict[str, Any], res.json())


async def mandate_prepare(
    relay_http_url: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """Returns unsigned mandate JSON and signing input for operator signing."""
    async with httpx.AsyncClient() as client:
        res = await client.post(f'{relay_http_url.rstrip("/")}/operator/prepare', json=fields)
        res.raise_for_status()
        return cast(dict[str, Any], res.json())
