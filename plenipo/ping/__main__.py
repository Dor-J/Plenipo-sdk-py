"""plenipo ping — relay connectivity self-test."""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
import time
from dataclasses import dataclass

from plenipo.errors.structured import PlenipoStructuredError, format_structured_error
from plenipo.identity.provision import ensure_identity
from plenipo.identity.sync import sync_identity_with_core
from plenipo.mcp.runtime import McpRuntime, load_mcp_config
from plenipo.ping.protocol import (
    DEFAULT_ECHO_DID,
    DEFAULT_ECHO_DOCUMENT_URL,
    build_ping_payload,
    is_ping_ack,
)


@dataclass(frozen=True)
class PingResult:
    """Successful ping outcome."""

    ok: bool
    sender_did: str
    recipient_did: str
    latency_ms: int
    envelope_id: str
    responder_did: str | None = None
    ack_envelope_id: str | None = None


def _apply_local_defaults() -> None:
    import os

    if sys.platform == 'win32':
        os.environ.setdefault('PLENIPO_CORE_URL', 'http://127.0.0.1:4000')
        os.environ.setdefault('PLENIPO_REGISTRY_URL', 'http://127.0.0.1:4001')
        os.environ.setdefault('PLENIPO_RELAY_URL', 'ws://127.0.0.1:4000/agent/websocket')


async def run_ping(
    *,
    recipient_did: str | None = None,
    recipient_document_url: str | None = None,
    timeout_ms: int = 120_000,
) -> PingResult:
    """Authenticates, sends a ping, and waits for acknowledgement."""
    _apply_local_defaults()
    target_did = recipient_did or DEFAULT_ECHO_DID
    document_url = recipient_document_url
    if document_url is None and target_did == DEFAULT_ECHO_DID:
        document_url = DEFAULT_ECHO_DOCUMENT_URL

    identity = await ensure_identity()
    synced, _ = await sync_identity_with_core(identity)
    config = await load_mcp_config()
    runtime = McpRuntime(config)

    started = time.monotonic()
    nonce = secrets.token_urlsafe(16)

    try:
        await runtime.ensure_connected()
        ack = await runtime.send(
            target_did,
            build_ping_payload(nonce, synced.did),
            document_url,
        )

        deadline = started + timeout_ms / 1000
        while time.monotonic() < deadline:
            for entry in runtime.drain_messages(limit=100):
                if entry.kind != 'deliver' or not entry.plaintext:
                    continue
                match = is_ping_ack(entry.plaintext, nonce)
                if match is None:
                    continue

                return PingResult(
                    ok=True,
                    sender_did=synced.did,
                    recipient_did=target_did,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    envelope_id=ack['envelope_id'],
                    responder_did=match.responder,
                    ack_envelope_id=match.envelope_id or entry.envelope_id,
                )

            await asyncio.sleep(0.25)

        raise PlenipoStructuredError(
            code='PING_TIMEOUT',
            message=f'Timed out waiting for ping acknowledgement from {target_did}',
            docs_url='https://plenipo.dev/errors#PING_TIMEOUT',
        )
    finally:
        await runtime.close()


def print_ping_result(result: PingResult) -> None:
    """Prints a human-readable ping summary."""
    print(f'ok: {str(result.ok).lower()}')
    print(f'sender_did: {result.sender_did}')
    print(f'recipient_did: {result.recipient_did}')
    print(f'latency_ms: {result.latency_ms}')
    print(f'envelope_id: {result.envelope_id}')
    if result.responder_did:
        print(f'responder_did: {result.responder_did}')
    if result.ack_envelope_id:
        print(f'ack_envelope_id: {result.ack_envelope_id}')


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='plenipo', description='Plenipo SDK utilities')
    subparsers = parser.add_subparsers(dest='command', required=True)
    ping = subparsers.add_parser('ping', help='Relay connectivity self-test')
    ping.add_argument('--recipient-did', default=None)
    ping.add_argument('--recipient-document-url', default=None)
    ping.add_argument('--timeout-ms', type=int, default=120_000)
    return parser


async def _run_ping_command(args: argparse.Namespace) -> int:
    try:
        result = await run_ping(
            recipient_did=args.recipient_did,
            recipient_document_url=args.recipient_document_url,
            timeout_ms=args.timeout_ms,
        )
        print_ping_result(result)
        return 0
    except Exception as exc:
        print(json.dumps(format_structured_error(exc), indent=2), file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    """Runs the plenipo CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == 'ping':
        return asyncio.run(_run_ping_command(args))
    parser.error(f'unknown command: {args.command}')
    return 2
