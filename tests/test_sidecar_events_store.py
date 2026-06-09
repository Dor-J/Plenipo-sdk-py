"""Tests for durable sidecar event storage."""

from __future__ import annotations

import asyncio
import json

import pytest

from plenipo.runtime.store import RuntimeStore
from plenipo.sidecar.events import DurableEventService
from plenipo.runtime.inbox_crypto import encrypt_plaintext, resolve_sidecar_store_key
from plenipo.sidecar.models import sidecar_event_to_api_dict


@pytest.mark.asyncio
async def test_list_sidecar_events_by_after_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    store = RuntimeStore()
    first = store.insert_sidecar_event(
        event_type='delivery_receipt',
        envelope_id='01A',
        payload={'type': 'delivery_receipt', 'envelope_id': '01A', 'charged_tokens': 1},
    )
    second = store.insert_sidecar_event(
        event_type='delivery_receipt',
        envelope_id='01B',
        payload={'type': 'delivery_receipt', 'envelope_id': '01B', 'charged_tokens': 2},
    )
    rows = store.list_sidecar_events(after_id=first, limit=10)
    assert len(rows) == 1
    assert rows[0].id == second


@pytest.mark.asyncio
async def test_wait_for_events_recovers_without_notify(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    store = RuntimeStore()
    service = DurableEventService(store=store)

    async def insert_later() -> None:
        await asyncio.sleep(0.05)
        store.insert_sidecar_event(
            event_type='delivery_receipt',
            envelope_id='01LATE',
            payload={'type': 'delivery_receipt', 'envelope_id': '01LATE'},
        )

    task = asyncio.create_task(insert_later())
    events, next_after_id = await service.wait_for_events(
        after_id=0,
        timeout_ms=500,
        limit=10,
        include_plaintext=False,
    )
    await task
    assert len(events) == 1
    assert events[0]['envelope_id'] == '01LATE'
    assert next_after_id >= 1


@pytest.mark.asyncio
async def test_wait_for_events_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    store = RuntimeStore()
    service = DurableEventService(store=store)
    events, next_after_id = await service.wait_for_events(
        after_id=0,
        timeout_ms=100,
        limit=10,
        include_plaintext=False,
    )
    assert events == []
    assert next_after_id == 0


def test_message_event_metadata_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    store = RuntimeStore()
    key = resolve_sidecar_store_key()
    ciphertext_b64, nonce_b64 = encrypt_plaintext('hello', key)
    store.insert_inbox_message(
        envelope_id='01MSG',
        sender_did='did:web:sender',
        recipient_did='did:web:recipient',
        received_at='2026-06-09T00:00:00Z',
        plaintext_ciphertext=ciphertext_b64,
        plaintext_nonce=nonce_b64,
        plaintext_alg='nacl-secretbox-v1',
        metadata={},
    )
    row = store.list_sidecar_events(after_id=0, limit=1)
    event_id = store.insert_sidecar_event(
        event_type='message',
        envelope_id='01MSG',
        payload={
            'type': 'message',
            'envelope_id': '01MSG',
            'sender_did': 'did:web:sender',
            'recipient_did': 'did:web:recipient',
            'received_at': '2026-06-09T00:00:00Z',
            'plaintext_ref': 'inbox:01MSG',
        },
    )
    stored = store.list_sidecar_events(after_id=event_id - 1, limit=1)[0]
    meta = sidecar_event_to_api_dict(stored, store=store, include_plaintext=False)
    assert meta['has_plaintext'] is True
    assert 'plaintext' not in meta
