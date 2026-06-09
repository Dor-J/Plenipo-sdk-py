"""Local runtime cursor state backed by runtime.sqlite."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from plenipo.identity.store import plenipo_home
from plenipo.runtime.store import RuntimeStore


@dataclass
class RuntimeState:
    """Non-secret runtime cursors persisted locally."""

    last_receipt_seen_at: str | None = None
    last_receipt_cursor: str | None = None
    last_message_seen_at: str | None = None
    version: int = 2


def runtime_state_path() -> Path:
    """Returns the legacy path to runtime-state.json."""
    return plenipo_home() / 'runtime-state.json'


def _load_legacy_json() -> RuntimeState | None:
    path = runtime_state_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    return RuntimeState(
        last_receipt_seen_at=_optional_str(raw.get('last_receipt_seen_at')),
        last_receipt_cursor=_optional_str(raw.get('last_receipt_cursor')),
        last_message_seen_at=_optional_str(raw.get('last_message_seen_at')),
        version=int(raw.get('version', 1)),
    )


def load_runtime_state(store: RuntimeStore | None = None) -> RuntimeState:
    """Loads runtime state from SQLite, migrating legacy JSON if needed."""
    owned = store is None
    db = store or RuntimeStore()
    try:
        legacy = _load_legacy_json()
        if legacy is not None:
            db.migrate_legacy_json_state(last_receipt_seen_at=legacy.last_receipt_seen_at)
            if legacy.last_receipt_cursor:
                db.set_state('last_receipt_cursor', legacy.last_receipt_cursor)
            if legacy.last_message_seen_at:
                db.set_state('last_message_seen_at', legacy.last_message_seen_at)

        return RuntimeState(
            last_receipt_seen_at=db.get_state('last_receipt_seen_at'),
            last_receipt_cursor=db.get_state('last_receipt_cursor'),
            last_message_seen_at=db.get_state('last_message_seen_at'),
            version=2,
        )
    finally:
        if owned:
            db.close()


def save_runtime_state(state: RuntimeState, store: RuntimeStore | None = None) -> None:
    """Persists runtime state to SQLite."""
    owned = store is None
    db = store or RuntimeStore()
    try:
        if state.last_receipt_seen_at:
            db.set_state('last_receipt_seen_at', state.last_receipt_seen_at)
        if state.last_receipt_cursor:
            db.set_state('last_receipt_cursor', state.last_receipt_cursor)
        if state.last_message_seen_at:
            db.set_state('last_message_seen_at', state.last_message_seen_at)
        db.set_state('version', str(state.version))
    finally:
        if owned:
            db.close()


def update_message_cursor(
    *,
    received_at: str | None = None,
    envelope_id: str | None = None,
    store: RuntimeStore | None = None,
) -> RuntimeState:
    """Updates and persists the last seen inbound message cursor."""
    owned = store is None
    db = store or RuntimeStore()
    try:
        state = load_runtime_state(db)
        timestamp = received_at or envelope_id
        if timestamp:
            state.last_message_seen_at = timestamp
            db.set_state('last_message_seen_at', timestamp)
        save_runtime_state(state, db)
        return state
    finally:
        if owned:
            db.close()


def update_receipt_cursor(
    *,
    delivered_at: str | None = None,
    received_at: str | None = None,
    cursor: str | None = None,
    store: RuntimeStore | None = None,
) -> RuntimeState:
    """Updates and persists receipt cursors."""
    owned = store is None
    db = store or RuntimeStore()
    try:
        state = load_runtime_state(db)
        timestamp = delivered_at or received_at
        if timestamp:
            state.last_receipt_seen_at = timestamp
            db.set_state('last_receipt_seen_at', timestamp)
        if cursor:
            state.last_receipt_cursor = cursor
            db.set_state('last_receipt_cursor', cursor)
        save_runtime_state(state, db)
        return state
    finally:
        if owned:
            db.close()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
