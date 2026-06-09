"""Durable SQLite runtime store under PLENIPO_HOME."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plenipo.identity.store import plenipo_home


def runtime_db_path() -> Path:
    """Returns the path to runtime.sqlite."""
    return plenipo_home() / 'runtime.sqlite'


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


@dataclass(frozen=True)
class OutboxRecord:
    """Sanitized outbox row for runtime inspection."""

    envelope_id: str
    recipient_did: str
    recipient_document_url: str | None
    created_at: str
    status: str
    ciphertext_bytes: int | None
    billable_kb: int | None
    charged_tokens: int | None
    balance_after: int | None
    sent_at: str | None
    delivered_at: str | None
    last_error: str | None


@dataclass(frozen=True)
class ReceiptRecord:
    """Sanitized receipt row for runtime inspection."""

    envelope_id: str
    sender_did: str
    recipient_did: str
    ciphertext_bytes: int | None
    billable_kb: int | None
    charged_tokens: int | None
    balance_after: int | None
    received_at: str | None
    delivered_at: str | None


class RuntimeStore:
    """Local SQLite store for outbox, receipts, and runtime cursors."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or runtime_db_path()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        """Closes the SQLite connection."""
        self._conn.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS outbox (
              envelope_id TEXT PRIMARY KEY,
              recipient_did TEXT NOT NULL,
              recipient_document_url TEXT,
              created_at TEXT NOT NULL,
              status TEXT NOT NULL,
              ciphertext_bytes INTEGER,
              billable_kb INTEGER,
              charged_tokens INTEGER,
              balance_after INTEGER,
              sent_at TEXT,
              delivered_at TEXT,
              last_error TEXT
            );

            CREATE TABLE IF NOT EXISTS receipts (
              envelope_id TEXT PRIMARY KEY,
              sender_did TEXT NOT NULL,
              recipient_did TEXT NOT NULL,
              ciphertext_bytes INTEGER,
              billable_kb INTEGER,
              charged_tokens INTEGER,
              balance_after INTEGER,
              received_at TEXT,
              delivered_at TEXT,
              raw_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS runtime_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def get_state(self, key: str) -> str | None:
        """Returns a runtime state value or None."""
        row = self._conn.execute(
            'SELECT value FROM runtime_state WHERE key = ?',
            (key,),
        ).fetchone()
        if row is None:
            return None
        return str(row['value'])

    def set_state(self, key: str, value: str) -> None:
        """Sets a runtime state key-value pair."""
        self._conn.execute(
            'INSERT INTO runtime_state (key, value) VALUES (?, ?) '
            'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, value),
        )
        self._conn.commit()

    def get_outbox(self, envelope_id: str) -> OutboxRecord | None:
        """Returns a single outbox row."""
        row = self._conn.execute(
            'SELECT * FROM outbox WHERE envelope_id = ?',
            (envelope_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_outbox(row)

    def insert_outbox_pending(
        self,
        *,
        envelope_id: str,
        recipient_did: str,
        recipient_document_url: str | None = None,
    ) -> None:
        """Inserts a pending outbox row before network send."""
        self._conn.execute(
            """
            INSERT INTO outbox (
              envelope_id, recipient_did, recipient_document_url,
              created_at, status
            ) VALUES (?, ?, ?, ?, 'pending')
            ON CONFLICT(envelope_id) DO NOTHING
            """,
            (envelope_id, recipient_did, recipient_document_url, _utc_now_iso()),
        )
        self._conn.commit()

    def mark_outbox_accepted(
        self,
        envelope_id: str,
        *,
        ciphertext_bytes: int | None,
        billable_kb: int | None,
        charged_tokens: int | None,
        balance_after: int | None,
    ) -> None:
        """Updates outbox row after relay accepts the send."""
        self._conn.execute(
            """
            UPDATE outbox SET
              status = 'accepted',
              ciphertext_bytes = ?,
              billable_kb = ?,
              charged_tokens = ?,
              balance_after = ?,
              sent_at = ?,
              last_error = NULL
            WHERE envelope_id = ?
            """,
            (
                ciphertext_bytes,
                billable_kb,
                charged_tokens,
                balance_after,
                _utc_now_iso(),
                envelope_id,
            ),
        )
        self._conn.commit()

    def mark_outbox_failed(self, envelope_id: str, *, last_error: str) -> None:
        """Marks an outbox row as failed."""
        self._conn.execute(
            """
            UPDATE outbox SET status = 'failed', last_error = ?
            WHERE envelope_id = ?
            """,
            (last_error[:500], envelope_id),
        )
        self._conn.commit()

    def mark_outbox_delivered(self, envelope_id: str, *, delivered_at: str | None = None) -> None:
        """Marks an outbox row as delivered after receipt observation."""
        self._conn.execute(
            """
            UPDATE outbox SET status = 'delivered', delivered_at = ?
            WHERE envelope_id = ?
            """,
            (delivered_at or _utc_now_iso(), envelope_id),
        )
        self._conn.commit()

    def list_outbox(self, *, status: str | None = None, limit: int = 100) -> list[OutboxRecord]:
        """Lists sanitized outbox rows."""
        if status:
            rows = self._conn.execute(
                'SELECT * FROM outbox WHERE status = ? ORDER BY created_at DESC LIMIT ?',
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                'SELECT * FROM outbox ORDER BY created_at DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [_row_to_outbox(row) for row in rows]

    def count_outbox_by_status(self) -> dict[str, int]:
        """Returns outbox counts grouped by status."""
        rows = self._conn.execute(
            'SELECT status, COUNT(*) AS count FROM outbox GROUP BY status',
        ).fetchall()
        return {str(row['status']): int(row['count']) for row in rows}

    def upsert_receipt(self, payload: dict[str, Any], *, sender_did: str) -> bool:
        """
        Upserts a receipt row. Returns True if newly inserted, False if duplicate.
        """
        envelope_id = str(payload.get('envelope_id', ''))
        if not envelope_id:
            return False

        existing = self._conn.execute(
            'SELECT envelope_id FROM receipts WHERE envelope_id = ?',
            (envelope_id,),
        ).fetchone()
        if existing is not None:
            return False

        self._conn.execute(
            """
            INSERT INTO receipts (
              envelope_id, sender_did, recipient_did,
              ciphertext_bytes, billable_kb, charged_tokens, balance_after,
              received_at, delivered_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                envelope_id,
                sender_did,
                str(payload.get('recipient_did') or ''),
                _optional_int(payload.get('ciphertext_bytes')),
                _optional_int(payload.get('billable_kb')),
                _optional_int(payload.get('charged_tokens')),
                _optional_int(payload.get('balance_after')),
                payload.get('received_at'),
                payload.get('delivered_at'),
                json.dumps(payload, separators=(',', ':')),
            ),
        )
        self._conn.commit()
        return True

    def has_receipt(self, envelope_id: str) -> bool:
        """Returns whether a receipt row exists."""
        row = self._conn.execute(
            'SELECT envelope_id FROM receipts WHERE envelope_id = ?',
            (envelope_id,),
        ).fetchone()
        return row is not None

    def list_receipts(self, *, limit: int = 100) -> list[ReceiptRecord]:
        """Lists sanitized receipt rows."""
        rows = self._conn.execute(
            'SELECT * FROM receipts ORDER BY delivered_at DESC, envelope_id DESC LIMIT ?',
            (limit,),
        ).fetchall()
        return [_row_to_receipt(row) for row in rows]

    def migrate_legacy_json_state(self, *, last_receipt_seen_at: str | None) -> None:
        """Migrates legacy runtime-state.json values into SQLite once."""
        if last_receipt_seen_at and not self.get_state('last_receipt_seen_at'):
            self.set_state('last_receipt_seen_at', last_receipt_seen_at)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _row_to_outbox(row: sqlite3.Row) -> OutboxRecord:
    return OutboxRecord(
        envelope_id=str(row['envelope_id']),
        recipient_did=str(row['recipient_did']),
        recipient_document_url=row['recipient_document_url'],
        created_at=str(row['created_at']),
        status=str(row['status']),
        ciphertext_bytes=row['ciphertext_bytes'],
        billable_kb=row['billable_kb'],
        charged_tokens=row['charged_tokens'],
        balance_after=row['balance_after'],
        sent_at=row['sent_at'],
        delivered_at=row['delivered_at'],
        last_error=row['last_error'],
    )


def _row_to_receipt(row: sqlite3.Row) -> ReceiptRecord:
    return ReceiptRecord(
        envelope_id=str(row['envelope_id']),
        sender_did=str(row['sender_did']),
        recipient_did=str(row['recipient_did']),
        ciphertext_bytes=row['ciphertext_bytes'],
        billable_kb=row['billable_kb'],
        charged_tokens=row['charged_tokens'],
        balance_after=row['balance_after'],
        received_at=row['received_at'],
        delivered_at=row['delivered_at'],
    )
