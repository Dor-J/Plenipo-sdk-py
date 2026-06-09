"""Tests for runtime SQLite store."""

from __future__ import annotations

import json

from plenipo.runtime.state import load_runtime_state, save_runtime_state, RuntimeState
from plenipo.runtime.store import RuntimeStore


def test_runtime_store_outbox_lifecycle(tmp_path: object) -> None:
    db = RuntimeStore(tmp_path / 'runtime.sqlite')  # type: ignore[operator]
    db.insert_outbox_pending(
        envelope_id='01OUT',
        recipient_did='did:web:localhost:agents:recipient',
    )
    pending = db.get_outbox('01OUT')
    assert pending is not None
    assert pending.status == 'pending'

    db.mark_outbox_accepted(
        '01OUT',
        ciphertext_bytes=105,
        billable_kb=1,
        charged_tokens=1,
        balance_after=999,
    )
    accepted = db.get_outbox('01OUT')
    assert accepted is not None
    assert accepted.status == 'accepted'
    assert accepted.charged_tokens == 1

    db.mark_outbox_delivered('01OUT', delivered_at='2026-06-09T10:00:00Z')
    delivered = db.get_outbox('01OUT')
    assert delivered is not None
    assert delivered.status == 'delivered'
    db.close()


def test_runtime_store_receipt_dedupe(tmp_path: object) -> None:
    db = RuntimeStore(tmp_path / 'runtime.sqlite')  # type: ignore[operator]
    payload = {
        'envelope_id': '01RCPT',
        'sender_did': 'did:web:localhost:agents:sender',
        'recipient_did': 'did:web:localhost:agents:recipient',
        'ciphertext_bytes': 105,
        'charged_tokens': 1,
        'delivered_at': '2026-06-09T10:00:00Z',
    }
    assert db.upsert_receipt(payload, sender_did='did:web:localhost:agents:sender') is True
    assert db.upsert_receipt(payload, sender_did='did:web:localhost:agents:sender') is False
    assert db.has_receipt('01RCPT') is True
    db.close()


def test_runtime_state_persisted_in_sqlite(tmp_path: object, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    save_runtime_state(RuntimeState(last_receipt_cursor='cursor-abc', last_receipt_seen_at='2026-06-09T10:00:00Z'))
    loaded = load_runtime_state()
    assert loaded.last_receipt_cursor == 'cursor-abc'
    assert loaded.last_receipt_seen_at == '2026-06-09T10:00:00Z'


def test_runtime_store_no_plaintext_by_default(tmp_path: object) -> None:
    db = RuntimeStore(tmp_path / 'runtime.sqlite')  # type: ignore[operator]
    rows = db.list_outbox()
    assert rows == []
    schema = db._conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'outbox'"
    ).fetchone()
    assert schema is not None
    assert 'plaintext' not in str(schema['sql']).lower()
    db.close()
