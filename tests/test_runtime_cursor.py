"""Tests for receipt cursor helpers."""

from __future__ import annotations

from plenipo.runtime.cursor import cursor_from_receipt_payload, encode_receipt_cursor


def test_encode_and_build_cursor_from_receipt() -> None:
    cursor = encode_receipt_cursor(
        delivered_at='2026-06-09T10:00:00Z',
        envelope_id='01ABC',
    )
    assert cursor
    rebuilt = cursor_from_receipt_payload(
        {'envelope_id': '01ABC', 'delivered_at': '2026-06-09T10:00:00Z'}
    )
    assert rebuilt == cursor
