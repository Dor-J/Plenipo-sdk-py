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


def test_cli_status_hides_secrets(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv('PLENIPO_HOME', str(tmp_path))
    printed: list[str] = []
    monkeypatch.setattr('builtins.print', lambda *args, **kwargs: printed.append(' '.join(str(a) for a in args)))

    async def fake_status() -> int:
        print('did: did:web:localhost:agents:test')
        print('core_registered: True')
        print('route_declared: True')
        print('connected: true')
        print('outbox_pending: 0')
        print('outbox_accepted: 1')
        print('outbox_delivered: 0')
        print('last_receipt_cursor: cursor-1')
        return 0

    monkeypatch.setattr('plenipo.agent.cli._show_status', fake_status)
    assert main(['status']) == 0
    output = '\n'.join(printed)
    assert 'auth_secret' not in output
    assert 'private' not in output.lower() or 'private keys' not in output.lower()
    assert 'outbox_accepted: 1' in output
