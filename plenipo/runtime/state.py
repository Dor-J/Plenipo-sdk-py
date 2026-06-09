"""Local runtime cursor state under PLENIPO_HOME."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from plenipo.identity.store import plenipo_home


@dataclass
class RuntimeState:
    """Non-secret runtime cursors persisted locally."""

    last_receipt_seen_at: str | None = None
    last_message_seen_at: str | None = None
    version: int = 1


def runtime_state_path() -> Path:
    """Returns the path to runtime-state.json."""
    return plenipo_home() / 'runtime-state.json'


def load_runtime_state() -> RuntimeState:
    """Loads runtime state from disk or returns defaults."""
    path = runtime_state_path()
    if not path.exists():
        return RuntimeState()

    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return RuntimeState()

    if not isinstance(raw, dict):
        return RuntimeState()

    return RuntimeState(
        last_receipt_seen_at=_optional_str(raw.get('last_receipt_seen_at')),
        last_message_seen_at=_optional_str(raw.get('last_message_seen_at')),
        version=int(raw.get('version', 1)),
    )


def save_runtime_state(state: RuntimeState) -> None:
    """Persists runtime state to disk."""
    path = runtime_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2), encoding='utf-8')


def update_receipt_cursor(timestamp: str) -> RuntimeState:
    """Updates and persists the last receipt cursor."""
    state = load_runtime_state()
    state.last_receipt_seen_at = timestamp
    save_runtime_state(state)
    return state


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
