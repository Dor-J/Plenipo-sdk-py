"""JSON models and sanitization helpers for the sidecar API."""

from __future__ import annotations

import os
from typing import Any

from plenipo.discover.records import RouteRecord
from plenipo.identity.route import route_from_document
from plenipo.identity.store import AgentIdentity
from plenipo.runtime.events import AgentEvent, DeliveryReceiptEvent, MessageEvent
from plenipo.runtime.state import load_runtime_state
from plenipo.runtime.store import OutboxRecord, ReceiptRecord, RuntimeStore

SIDECAR_VERSION = '0.2.1'
SERVICE_NAME = 'plenipo-agent-sidecar'

SECRET_KEYS = frozenset(
    {
        'auth_secret_b64',
        'enc_secret_b64',
        'private_key',
        'privateKey',
        'ciphertext',
        'auth_secret',
        'enc_secret',
    }
)


def public_route_from_identity(identity: AgentIdentity) -> dict[str, Any]:
    """Returns public route metadata from a local identity document."""
    route = route_from_document(identity.document)
    return {
        'did': identity.did,
        'protocols': route['protocols'],
        'capabilities': route['capabilities'],
        'encryption': route['encryption'],
        'payment': route['payment'],
        'limits': route['limits'],
    }


def route_record_to_dict(record: RouteRecord) -> dict[str, Any]:
    """Serializes a discovery RouteRecord for API output."""
    return dict(record)


def outbox_record_to_dict(row: OutboxRecord) -> dict[str, Any]:
    """Serializes a sanitized outbox row."""
    return {
        'envelope_id': row.envelope_id,
        'recipient_did': row.recipient_did,
        'recipient_document_url': row.recipient_document_url,
        'created_at': row.created_at,
        'status': row.status,
        'ciphertext_bytes': row.ciphertext_bytes,
        'billable_kb': row.billable_kb,
        'charged_tokens': row.charged_tokens,
        'balance_after': row.balance_after,
        'sent_at': row.sent_at,
        'delivered_at': row.delivered_at,
        'last_error': row.last_error,
    }


def receipt_record_to_dict(row: ReceiptRecord) -> dict[str, Any]:
    """Serializes a sanitized receipt row."""
    return {
        'envelope_id': row.envelope_id,
        'sender_did': row.sender_did,
        'recipient_did': row.recipient_did,
        'ciphertext_bytes': row.ciphertext_bytes,
        'billable_kb': row.billable_kb,
        'charged_tokens': row.charged_tokens,
        'balance_after': row.balance_after,
        'received_at': row.received_at,
        'delivered_at': row.delivered_at,
    }


def event_to_dict(event: AgentEvent) -> dict[str, Any] | None:
    """Maps runtime events to sidecar API event payloads."""
    if isinstance(event, MessageEvent):
        return {
            'type': 'message',
            'envelope_id': event.envelope_id,
            'sender_did': event.sender_did,
            'plaintext': event.plaintext,
        }

    if isinstance(event, DeliveryReceiptEvent):
        payload: dict[str, Any] = {
            'type': 'delivery_receipt',
            'envelope_id': event.envelope_id,
            'charged_tokens': event.charged_tokens,
        }
        if event.delivered_at is not None:
            payload['delivered_at'] = event.delivered_at
        elif event.received_at is not None:
            payload['delivered_at'] = event.received_at
        if event.ciphertext_bytes is not None:
            payload['ciphertext_bytes'] = event.ciphertext_bytes
        if event.billable_kb is not None:
            payload['billable_kb'] = event.billable_kb
        if event.balance_after is not None:
            payload['balance_after'] = event.balance_after
        return payload

    return None


def document_has_route(document: dict[str, Any]) -> bool:
    """Returns True when the DID document declares Plenipo route metadata."""
    for service in document.get('service') or []:
        if isinstance(service, dict) and service.get('type') == 'PlenipoAgent':
            if service.get('protocols'):
                return True
    return False


def build_status_payload(
    *,
    identity: AgentIdentity,
    connected: bool,
    store: RuntimeStore,
) -> dict[str, Any]:
    """Builds the sanitized /status response."""
    state = load_runtime_state(store)
    counts = store.count_outbox_by_status()
    receipt_count = len(store.list_receipts(limit=10_000))
    cursor = state.last_receipt_cursor or state.last_receipt_seen_at

    return {
        'did': identity.did,
        'connected': connected,
        'core_registered': identity.core_registered,
        'route_declared': document_has_route(identity.document),
        'outbox': {
            'pending': counts.get('pending', 0),
            'accepted': counts.get('accepted', 0),
            'delivered': counts.get('delivered', 0),
            'failed': counts.get('failed', 0),
        },
        'receipts': {
            'count': receipt_count,
            'last_cursor': cursor,
        },
        'endpoints': {
            'core_url': identity.core_url or os.environ.get('PLENIPO_CORE_URL', ''),
            'registry_url': identity.registry_url or os.environ.get('PLENIPO_REGISTRY_URL', ''),
            'relay_url': identity.relay_url or os.environ.get('PLENIPO_RELAY_URL', ''),
        },
    }


def send_ack_to_dict(ack: dict[str, Any]) -> dict[str, Any]:
    """Maps a relay send ack to the sidecar /send response."""
    return {
        'envelope_id': str(ack.get('envelope_id', '')),
        'ciphertext_bytes': ack.get('ciphertext_bytes'),
        'billable_kb': ack.get('billable_kb'),
        'charged_tokens': ack.get('charged_tokens'),
        'balance_after': ack.get('balance_after'),
        'status': 'accepted',
    }


def contains_secret_keys(payload: Any) -> bool:
    """Returns True when a nested payload contains known secret field names."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key) in SECRET_KEYS:
                return True
            if contains_secret_keys(value):
                return True
        return False

    if isinstance(payload, list):
        return any(contains_secret_keys(item) for item in payload)

    return False
