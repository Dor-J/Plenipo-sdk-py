"""Typed runtime events for Agent Runtime v0."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AgentEvent:
    """Base runtime event."""

    type: Literal['connect', 'disconnect', 'message', 'delivery_receipt', 'error']


@dataclass(frozen=True)
class ConnectEvent(AgentEvent):
    """Emitted when the relay connection is established."""

    type: Literal['connect'] = 'connect'
    did: str = ''


@dataclass(frozen=True)
class DisconnectEvent(AgentEvent):
    """Emitted when the relay connection is lost."""

    type: Literal['disconnect'] = 'disconnect'
    reason: str = ''


@dataclass(frozen=True)
class MessageEvent(AgentEvent):
    """Emitted when an encrypted message is received and decrypted."""

    type: Literal['message'] = 'message'
    envelope_id: str = ''
    sender_did: str = ''
    recipient_did: str = ''
    plaintext: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class DeliveryReceiptEvent(AgentEvent):
    """Emitted when a delivery receipt is observed live or recovered."""

    type: Literal['delivery_receipt'] = 'delivery_receipt'
    envelope_id: str = ''
    sender_did: str | None = None
    recipient_did: str | None = None
    ciphertext_bytes: int | None = None
    billable_kb: int | None = None
    charged_tokens: int | None = None
    balance_after: int | None = None
    received_at: str | None = None
    delivered_at: str | None = None
    recovered: bool = False


@dataclass(frozen=True)
class ErrorEvent(AgentEvent):
    """Emitted when the runtime encounters a recoverable error."""

    type: Literal['error'] = 'error'
    message: str = ''
