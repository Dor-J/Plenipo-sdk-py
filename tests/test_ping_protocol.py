"""Tests for ping protocol helpers."""

from __future__ import annotations

from plenipo.ping.protocol import (
    PING_ACK_KIND,
    PING_KIND,
    build_ping_ack_payload,
    build_ping_payload,
    is_ping_ack,
    parse_ping_request,
)


def test_build_ping_and_ack_payloads() -> None:
    ping = build_ping_payload('nonce-1', 'did:web:localhost:agents:a')
    assert '"kind":"plenipo.ping"' in ping.replace(' ', '')

    ack = build_ping_ack_payload('nonce-1', 'did:web:echo.plenipo.dev', '01ENV')
    assert PING_ACK_KIND in ack


def test_is_ping_ack_matches_nonce() -> None:
    ack = build_ping_ack_payload('abc', 'did:web:echo.plenipo.dev', '01ENV')
    match = is_ping_ack(ack, 'abc')
    assert match is not None
    assert match.responder == 'did:web:echo.plenipo.dev'
    assert is_ping_ack(ack, 'wrong') is None


def test_parse_ping_request() -> None:
    ping = build_ping_payload('abc', 'did:web:localhost:agents:a')
    parsed = parse_ping_request(ping)
    assert parsed == {'nonce': 'abc', 'sender': 'did:web:localhost:agents:a'}
    assert parse_ping_request('not-json') is None
    assert PING_KIND == 'plenipo.ping'
