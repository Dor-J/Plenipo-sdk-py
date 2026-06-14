"""Shared plenipo ping / echo protocol constants."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

DEFAULT_ECHO_DID = 'did:web:echo.plenipo.dev'
DEFAULT_ECHO_DOCUMENT_URL = 'https://echo.plenipo.dev/.well-known/did.json'
PING_KIND = 'plenipo.ping'
PING_ACK_KIND = 'plenipo.ping.ack'


def build_ping_payload(nonce: str, sender_did: str) -> str:
    """Builds a ping request payload."""
    return json.dumps({'kind': PING_KIND, 'nonce': nonce, 'sender': sender_did}, separators=(',', ':'))


@dataclass(frozen=True)
class PingAckMatch:
    """Parsed ping acknowledgement."""

    responder: str
    envelope_id: str | None = None


def is_ping_ack(plaintext: str, nonce: str) -> PingAckMatch | None:
    """Returns acknowledgement details when plaintext matches the ping nonce."""
    try:
        payload = json.loads(plaintext)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get('kind') != PING_ACK_KIND or payload.get('nonce') != nonce:
        return None

    envelope_id = payload.get('received_envelope_id')
    return PingAckMatch(
        responder=str(payload.get('responder', '')),
        envelope_id=envelope_id if isinstance(envelope_id, str) else None,
    )


def parse_ping_request(plaintext: str) -> dict[str, str] | None:
    """Returns ping request fields when plaintext is a valid ping."""
    try:
        payload = json.loads(plaintext)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    if payload.get('kind') != PING_KIND or not isinstance(payload.get('nonce'), str):
        return None

    sender = payload.get('sender')
    return {
        'nonce': payload['nonce'],
        'sender': sender if isinstance(sender, str) else '',
    }


def build_ping_ack_payload(nonce: str, responder_did: str, received_envelope_id: str) -> str:
    """Builds a ping acknowledgement payload."""
    return json.dumps(
        {
            'kind': PING_ACK_KIND,
            'nonce': nonce,
            'responder': responder_did,
            'received_envelope_id': received_envelope_id,
        },
        separators=(',', ':'),
    )
