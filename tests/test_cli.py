"""CLI tests for plenipo-agent."""

from __future__ import annotations

from plenipo.agent.cli import _print_event, main
from plenipo.runtime.events import ConnectEvent, DeliveryReceiptEvent, MessageEvent


def test_print_event_sanitized_output(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    printed: list[str] = []
    monkeypatch.setattr(
        'builtins.print',
        lambda *args, **kwargs: printed.append(' '.join(str(a) for a in args)),
    )

    _print_event(ConnectEvent(did='did:web:localhost:agents:test'), print_events=True, print_plaintext=False)
    _print_event(
        DeliveryReceiptEvent(
            envelope_id='01RCPT',
            ciphertext_bytes=105,
            billable_kb=1,
            charged_tokens=1,
            balance_after=999,
            recovered=True,
        ),
        print_events=True,
        print_plaintext=False,
    )
    _print_event(
        MessageEvent(envelope_id='01MSG', sender_did='did:web:localhost:agents:sender', plaintext='secret'),
        print_events=True,
        print_plaintext=False,
    )

    output = '\n'.join(printed)
    assert 'auth_secret' not in output
    assert 'secret' not in output
    assert '[connect]' in output
    assert '[receipt]' in output
    assert 'tokens=1' in output
    assert '[message]' in output
    assert 'envelope_id=01MSG' in output


def test_cli_run_exits_cleanly(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_run_agent(_args: object) -> int:
        return 0

    monkeypatch.setattr('plenipo.agent.cli._run_agent', fake_run_agent)
    assert main(['run']) == 0
