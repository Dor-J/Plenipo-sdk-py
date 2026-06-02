"""Create a laptop-local Plenipo identity for local-lab testing."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from plenipo.did import DidCreateResult, create_did_document


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a laptop-local Plenipo identity.')
    parser.add_argument('--host', required=True, help='Controlled DID host, for example agents.example.com')
    parser.add_argument('--path', required=True, help='DID path, for example local/python-a')
    parser.add_argument(
        '--relay-url',
        required=True,
        help='Relay WebSocket URL, for example ws://192.168.0.251:4000/agent/websocket',
    )
    parser.add_argument('--registry-url', required=True, help='Registry URL, for example http://192.168.0.251:4001')
    parser.add_argument('--out', help='Output directory. Defaults to .plenipo-local/<path>.')
    args = parser.parse_args()

    path_segments = _split_path(args.path)
    out_dir = Path(args.out or f'.plenipo-local/{args.path.replace("/", "-").replace(":", "-")}').resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    identity = create_did_document(args.host, args.relay_url, path_segments=path_segments)
    public_path = out_dir / 'did.json'
    env_path = out_dir / 'private.env'

    public_path.write_text(json.dumps(identity.document, indent=2) + '\n', encoding='utf-8')
    env_path.write_text(_private_env(identity, args.relay_url, args.registry_url), encoding='utf-8')
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass

    print(f'DID: {identity.did}')
    print(f'Public DID document: {public_path}')
    print(f'Private env file: {env_path}')
    print('Private keys were written only to the private env file. Do not commit it.')
    return 0


def _private_env(identity: DidCreateResult, relay_url: str, registry_url: str) -> str:
    lines = [
        f'PLENIPO_DID={identity.did}',
        f'PLENIPO_AUTH_SECRET_B64={identity.auth_secret_b64}',
        f'PLENIPO_ENC_SECRET_B64={identity.enc_secret_b64}',
        f'PLENIPO_DID_DOCUMENT_URL={identity.document_url}',
        f'PLENIPO_RELAY_URL={relay_url}',
        f'PLENIPO_REGISTRY_URL={registry_url}',
    ]

    if relay_url.startswith('ws://') and not _is_loopback_relay(relay_url):
        lines.append('PLENIPO_ALLOW_INSECURE_RELAY=true')

    lines.append('')
    return '\n'.join(lines)


def _split_path(path: str) -> list[str]:
    return [segment.strip() for segment in path.replace(':', '/').split('/') if segment.strip()]


def _is_loopback_relay(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.hostname in {'localhost', '127.0.0.1', '::1'}


if __name__ == '__main__':
    raise SystemExit(main())
