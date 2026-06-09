"""Command-line interface for Agent Runtime v0."""

from __future__ import annotations

import argparse
import asyncio
import sys

from plenipo.runtime import PlenipoAgentRuntime
from plenipo.runtime.events import DeliveryReceiptEvent, MessageEvent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='plenipo-agent')
    subparsers = parser.add_subparsers(dest='command', required=True)

    run_parser = subparsers.add_parser('run', help='Run the autonomous agent runtime')
    run_parser.add_argument('--capability', default='mcp', help='Declared capability label')
    run_parser.add_argument('--protocol', default='plenipo.message.v1', help='Declared protocol')
    run_parser.add_argument(
        '--print-events',
        action='store_true',
        help='Print connect/disconnect/error events',
    )
    run_parser.add_argument(
        '--print-plaintext',
        action='store_true',
        help='Print decrypted message plaintext (opt-in)',
    )
    return parser


def _print_event(event: object, *, print_events: bool, print_plaintext: bool) -> None:
    if event.type == 'connect' and print_events:
        print(f'[connect] did={event.did}')
        return

    if event.type == 'disconnect' and print_events:
        print(f'[disconnect] reason={event.reason}')
        return

    if event.type == 'error' and print_events:
        print(f'[error] {event.message}')
        return

    if event.type == 'message':
        msg = event
        assert isinstance(msg, MessageEvent)
        print(f'[message] envelope_id={msg.envelope_id} sender={msg.sender_did}')
        if print_plaintext and msg.plaintext is not None:
            print(msg.plaintext)
        return

    if event.type == 'delivery_receipt':
        receipt = event
        assert isinstance(receipt, DeliveryReceiptEvent)
        source = 'recovered' if receipt.recovered else 'live'
        print(
            '[receipt] '
            f'envelope_id={receipt.envelope_id} '
            f'bytes={receipt.ciphertext_bytes} '
            f'kb={receipt.billable_kb} '
            f'tokens={receipt.charged_tokens} '
            f'balance_after={receipt.balance_after} '
            f'source={source}'
        )


async def _run_agent(args: argparse.Namespace) -> int:
    if sys.platform == 'win32':
        import os

        os.environ.setdefault('PLENIPO_CORE_URL', 'http://127.0.0.1:4000')
        os.environ.setdefault('PLENIPO_REGISTRY_URL', 'http://127.0.0.1:4001')
        os.environ.setdefault('PLENIPO_RELAY_URL', 'ws://127.0.0.1:4000/agent/websocket')

    async with PlenipoAgentRuntime() as agent:
        print('[ready] agent runtime connected')
        async for event in agent.events():
            _print_event(
                event,
                print_events=args.print_events,
                print_plaintext=args.print_plaintext,
            )


def main(argv: list[str] | None = None) -> int:
    """Runs the plenipo-agent CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == 'run':
        try:
            asyncio.run(_run_agent(args))
        except KeyboardInterrupt:
            return 0
        return 0

    parser.error(f'unknown command: {args.command}')
    return 2
