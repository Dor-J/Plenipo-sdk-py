"""Tests for plenipo ping CLI."""

from __future__ import annotations

import pytest

from plenipo.errors.structured import PlenipoStructuredError
from plenipo.ping.__main__ import PingResult, main, print_ping_result, run_ping


async def test_run_ping_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRuntime:
        def __init__(self, _config: object) -> None:
            self.closed = False

        async def ensure_connected(self) -> object:
            return object()

        async def send(self, *_args: object, **_kwargs: object) -> dict[str, str]:
            return {'envelope_id': '01PING', 'status': 'queued'}

        def drain_messages(self, *_args: object, **_kwargs: object) -> list[object]:
            from plenipo.mcp.runtime import BufferedMessage

            return [
                BufferedMessage(
                    kind='deliver',
                    envelope_id='01ACK',
                    received_at_iso='2026-06-14T00:00:00+00:00',
                    plaintext=(
                        '{"kind":"plenipo.ping.ack","nonce":"test-nonce",'
                        '"responder":"did:web:echo.plenipo.dev",'
                        '"received_envelope_id":"01PING"}'
                    ),
                )
            ]

        async def close(self) -> None:
            self.closed = True

    class FakeIdentity:
        did = 'did:web:localhost:agents:sender'
        document: dict[str, object] = {'service': []}
        core_registered = True

    async def fake_ensure_identity() -> FakeIdentity:
        return FakeIdentity()

    async def fake_sync(_identity: object) -> tuple[FakeIdentity, object]:
        return FakeIdentity(), None

    async def fake_load_config() -> object:
        return object()

    monkeypatch.setattr('plenipo.ping.__main__.ensure_identity', fake_ensure_identity)
    monkeypatch.setattr('plenipo.ping.__main__.sync_identity_with_core', fake_sync)
    monkeypatch.setattr('plenipo.ping.__main__.load_mcp_config', fake_load_config)
    monkeypatch.setattr('plenipo.ping.__main__.McpRuntime', FakeRuntime)
    monkeypatch.setattr('plenipo.ping.__main__.secrets.token_urlsafe', lambda _n: 'test-nonce')

    result = await run_ping(timeout_ms=1000)
    assert result.ok is True
    assert result.envelope_id == '01PING'
    assert result.responder_did == 'did:web:echo.plenipo.dev'


def test_print_ping_result(capsys: pytest.CaptureFixture[str]) -> None:
    print_ping_result(
        PingResult(
            ok=True,
            sender_did='did:web:localhost:agents:sender',
            recipient_did='did:web:echo.plenipo.dev',
            latency_ms=25,
            envelope_id='01PING',
            responder_did='did:web:echo.plenipo.dev',
            ack_envelope_id='01ACK',
        )
    )
    output = capsys.readouterr().out
    assert 'latency_ms: 25' in output
    assert 'envelope_id: 01PING' in output


def test_ping_cli_returns_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_ping(**_kwargs: object) -> PingResult:
        raise PlenipoStructuredError(
            code='PING_TIMEOUT',
            message='timed out',
            docs_url='https://plenipo.dev/errors#PING_TIMEOUT',
        )

    monkeypatch.setattr('plenipo.ping.__main__.run_ping', fake_run_ping)
    code = main(['ping', '--timeout-ms', '1'])
    assert code == 2


def test_ping_cli_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_ping(**_kwargs: object) -> PingResult:
        return PingResult(
            ok=True,
            sender_did='did:web:localhost:agents:sender',
            recipient_did='did:web:echo.plenipo.dev',
            latency_ms=10,
            envelope_id='01PING',
        )

    monkeypatch.setattr('plenipo.ping.__main__.run_ping', fake_run_ping)
    assert main(['ping']) == 0
