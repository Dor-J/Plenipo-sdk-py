"""Long-lived echo responder for did:web:echo.plenipo.dev."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from plenipo.mcp.runtime import McpRuntime, load_mcp_config_from_env
from plenipo.ping.protocol import build_ping_ack_payload, parse_ping_request


async def main() -> int:
    parser = argparse.ArgumentParser(description='Plenipo echo responder')
    parser.add_argument('--env', help='Private env file from generate-echo-agent')
    parser.add_argument('--timeout-ms', type=int, default=86_400_000)
    args = parser.parse_args()

    if args.env:
        _load_env_file(Path(args.env))

    runtime = McpRuntime(load_mcp_config_from_env())
    await runtime.ensure_connected()
    print(f'Echo responder connected as {os.environ["PLENIPO_DID"]}')

    deadline = asyncio.get_running_loop().time() + args.timeout_ms / 1000
    while asyncio.get_running_loop().time() < deadline:
        for entry in runtime.drain_messages(limit=100):
            if entry.kind != 'deliver' or not entry.plaintext or not entry.sender_did:
                continue

            ping = parse_ping_request(entry.plaintext)
            if ping is None or not ping['sender']:
                continue

            ack = await runtime.send(
                ping['sender'],
                build_ping_ack_payload(
                    ping['nonce'],
                    os.environ['PLENIPO_DID'],
                    entry.envelope_id,
                ),
            )
            print(
                f'Ack sent to {ping["sender"]} envelope {ack["envelope_id"]} ({ack["status"]}).'
            )
            return 0

        await asyncio.sleep(0.5)

    raise TimeoutError('Timed out waiting for plenipo.ping request')


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if separator:
            os.environ[key] = value


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
