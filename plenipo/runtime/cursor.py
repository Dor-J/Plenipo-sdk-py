"""Receipt cursor helpers for runtime replay."""

from __future__ import annotations

import json
from typing import Any

from plenipo.crypto import base64url


def encode_receipt_cursor(*, delivered_at: str, envelope_id: str) -> str:
    """Encodes an opaque receipt list cursor."""
    payload = json.dumps(
        {'delivered_at': delivered_at, 'envelope_id': envelope_id},
        separators=(',', ':'),
    ).encode('utf-8')
    return base64url.encode(payload)


def cursor_from_receipt_payload(payload: dict[str, Any]) -> str | None:
    """Builds a cursor from a receipt payload when timestamps are present."""
    delivered_at = payload.get('delivered_at') or payload.get('received_at')
    envelope_id = payload.get('envelope_id')
    if not delivered_at or not envelope_id:
        return None
    return encode_receipt_cursor(
        delivered_at=str(delivered_at),
        envelope_id=str(envelope_id),
    )
