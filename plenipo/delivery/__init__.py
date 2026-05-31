"""Delivery status and receipt helpers for v0.4."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

import httpx

DeliveryStatus = Literal[
    'queued',
    'delivered',
    'receipt_confirmed',
    'expired',
    'not_found',
]


class DeliveryStatusResponse(TypedDict, total=False):
    """REST delivery status response."""

    type: str
    v: str
    envelope_id: str
    status: DeliveryStatus
    queued_until: str
    received_at: str


async def get_delivery_status(relay_http_url: str, envelope_id: str) -> DeliveryStatusResponse:
    """Fetches delivery status via REST."""
    async with httpx.AsyncClient() as client:
        res = await client.get(f'{relay_http_url}/v1/delivery/{envelope_id}')
        res.raise_for_status()
        return res.json()


def build_receipt(envelope_id: str) -> dict[str, str]:
    """Builds a message.receipt payload for the relay channel."""
    return {'envelope_id': envelope_id}
