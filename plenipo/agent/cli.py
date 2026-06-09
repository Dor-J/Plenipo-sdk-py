"""Command-line interface for Agent Runtime v0.1 and Sidecar v0.2."""

from __future__ import annotations

import argparse
import asyncio
import sys

from plenipo.identity.provision import ensure_identity
from plenipo.identity.sync import sync_identity_with_core
from plenipo.runtime import PlenipoAgentRuntime
from plenipo.runtime.events import DeliveryReceiptEvent, MessageEvent
from plenipo.runtime.state import load_runtime_state
from plenipo.runtime.store import RuntimeStore


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

    subparsers.add_parser('status', help='Show runtime status without secrets')
    subparsers.add_parser('outbox', help='List sanitized outbox rows')
    subparsers.add_parser('receipts', help='List sanitized receipt rows')

    sidecar_parser = subparsers.add_parser('sidecar', help='Run local HTTP sidecar API')
    sidecar_parser.add_argument('--host', default='127.0.0.1', help='Bind host (default 127.0.0.1)')
    sidecar_parser.add_argument('--port', type=int, default=8787, help='Bind port (default 8787)')
    sidecar_parser.add_argument('--capability', default='mcp', help='Declared capability label')
    sidecar_parser.add_argument(
        '--protocol',
        default='plenipo.message.v1',
        help='Declared protocol',
    )
    sidecar_parser.add_argument(
        '--allow-remote-bind',
        action='store_true',
        help='Allow binding to non-localhost interfaces',
    )
    sidecar_parser.add_argument(
        '--token',
        default=None,
        help='Bearer token override (default: env, token file, or generated)',
    )
    sidecar_parser.add_argument(
        '--no-auth',
        action='store_true',
        help='Disable bearer auth (localhost development only)',
    )
    sidecar_parser.add_argument(
        '--print-token',
        action='store_true',
        help='Print bearer token to stderr on startup',
    )
    sidecar_parser.add_argument(
        '--allow-origin',
        action='append',
        default=[],
        help='Allowed browser Origin header (repeatable)',
    )

    token_parser = subparsers.add_parser('sidecar-token', help='Show sidecar token file status')
    token_parser.add_argument(
        '--show',
        action='store_true',
        help='Print bearer token to stdout (with stderr warning)',
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


def _document_has_route(document: dict[str, object]) -> bool:
    for service in document.get('service') or []:
        if isinstance(service, dict) and service.get('type') == 'PlenipoAgent':
            if service.get('protocols'):
                return True
    return False


async def _run_agent(args: argparse.Namespace) -> int:
    _apply_local_defaults()

    async with PlenipoAgentRuntime() as agent:
        print('[ready] agent runtime connected')
        async for event in agent.events():
            _print_event(
                event,
                print_events=args.print_events,
                print_plaintext=args.print_plaintext,
            )


async def _show_status() -> int:
    _apply_local_defaults()
    store = RuntimeStore()
    try:
        identity = await ensure_identity()
        synced, _ = await sync_identity_with_core(identity)
        state = load_runtime_state(store)
        counts = store.count_outbox_by_status()

        connected = False
        runtime = PlenipoAgentRuntime()
        try:
            await runtime.ensure_ready()
            connected = runtime._client is not None and runtime._client.connected
            await runtime.close()
        except Exception:
            connected = False
            try:
                await runtime.close()
            except Exception:
                pass

        print(f'did: {synced.did}')
        print(f'core_registered: {synced.core_registered}')
        print(f'route_declared: {_document_has_route(synced.document)}')
        print(f'connected: {str(connected).lower()}')
        print(f'outbox_pending: {counts.get("pending", 0)}')
        print(f'outbox_accepted: {counts.get("accepted", 0)}')
        print(f'outbox_delivered: {counts.get("delivered", 0)}')
        print(f'outbox_failed: {counts.get("failed", 0)}')
        cursor = state.last_receipt_cursor or state.last_receipt_seen_at or ''
        print(f'last_receipt_cursor: {cursor}')
        return 0
    finally:
        store.close()


def _show_outbox() -> int:
    store = RuntimeStore()
    try:
        for row in store.list_outbox(limit=100):
            print(
                f'{row.envelope_id} status={row.status} recipient={row.recipient_did} '
                f'tokens={row.charged_tokens} delivered_at={row.delivered_at}'
            )
        return 0
    finally:
        store.close()


def _show_receipts() -> int:
    store = RuntimeStore()
    try:
        for row in store.list_receipts(limit=100):
            print(
                f'{row.envelope_id} tokens={row.charged_tokens} '
                f'bytes={row.ciphertext_bytes} delivered_at={row.delivered_at}'
            )
        return 0
    finally:
        store.close()


def _apply_local_defaults() -> None:
    if sys.platform == 'win32':
        import os

        os.environ.setdefault('PLENIPO_CORE_URL', 'http://127.0.0.1:4000')
        os.environ.setdefault('PLENIPO_REGISTRY_URL', 'http://127.0.0.1:4001')
        os.environ.setdefault('PLENIPO_RELAY_URL', 'ws://127.0.0.1:4000/agent/websocket')


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

    if args.command == 'status':
        return asyncio.run(_show_status())

    if args.command == 'outbox':
        return _show_outbox()

    if args.command == 'receipts':
        return _show_receipts()

    if args.command == 'sidecar':
        return _run_sidecar(args)

    if args.command == 'sidecar-token':
        return _show_sidecar_token(args)

    parser.error(f'unknown command: {args.command}')
    return 2


def _show_sidecar_token(args: argparse.Namespace) -> int:
    from plenipo.sidecar.auth import read_sidecar_token_file, sidecar_token_path

    path = sidecar_token_path()
    exists = path.is_file()
    print(f'Token file: {path}')
    print(f'Exists: {str(exists).lower()}')
    if args.show:
        print('WARNING: displaying sidecar bearer token', file=sys.stderr)
        if exists:
            token = read_sidecar_token_file(path)
            if token:
                print(token)
    return 0


def _run_sidecar(args: argparse.Namespace) -> int:
    from plenipo.sidecar.config import SidecarConfig, validate_bind_host, validate_no_auth_bind
    from plenipo.sidecar.server import run_sidecar

    _apply_local_defaults()
    config = SidecarConfig(
        host=args.host,
        port=args.port,
        capability=args.capability,
        protocol=args.protocol,
        allow_remote_bind=args.allow_remote_bind,
        token=args.token,
        no_auth=args.no_auth,
        print_token=args.print_token,
        allowed_origins=tuple(args.allow_origin),
    )
    try:
        validate_bind_host(config.host, allow_remote_bind=config.allow_remote_bind)
        validate_no_auth_bind(config.host, no_auth=config.no_auth)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    run_sidecar(config)
    return 0
