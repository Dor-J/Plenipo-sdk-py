"""WebSocket relay client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import websockets
from nacl.public import Box, PublicKey, SealedBox
from nacl.signing import SigningKey

from plenipo.crypto import base64url, signing_input
from plenipo.payments import build_relay_payment

MessageHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


class PlenipoClient:
    """Programmatic client for the Plenipo relay."""

    def __init__(
        self,
        *,
        did: str,
        auth_secret_b64: str,
        did_document_url: str,
        relay_url: str = 'ws://localhost:4000/agent/websocket',
    ) -> None:
        self.did = did
        self._signing = SigningKey(base64url.decode(auth_secret_b64))
        self.did_document_url = did_document_url
        parsed = urlparse(relay_url.replace('ws://', 'http://').replace('wss://', 'https://'))
        self._http_base = f'{parsed.scheme}://{parsed.netloc}'
        self._ws_url = relay_url
        self._handlers: list[MessageHandler] = []
        self._ws: Any = None
        self._join_ref = '1'
        self._ref = 2

    def on_message(self, handler: MessageHandler) -> None:
        """Registers a handler for incoming envelopes."""
        self._handlers.append(handler)

    async def connect(self) -> None:
        """Authenticates and joins relay:inbox."""
        async with httpx.AsyncClient() as client:
            challenge = (
                await client.post(
                    f'{self._http_base}/auth/challenge',
                    json={'did': self.did},
                )
            ).json()

        nonce = challenge['nonce']
        signature = self._signing.sign(base64url.decode(nonce)).signature
        params = urlencode(
            {
                'did': self.did,
                'nonce': nonce,
                'signature': base64url.encode(signature),
                'did_document_url': self.did_document_url,
                'vsn': '2.0.0',
            }
        )
        ws_target = f'{self._ws_url}?{params}'
        self._ws = await websockets.connect(ws_target)
        await self._send_phoenix(self._join_ref, None, 'relay:inbox', 'phx_join', {})
        joined = asyncio.Event()

        async def reader() -> None:
            assert self._ws is not None
            async for raw in self._ws:
                msg = json.loads(raw)
                await self._handle_phoenix(msg, joined)

        asyncio.create_task(reader())
        await joined.wait()

    async def send(self, recipient_did: str, plaintext: str, recipient_public_key: bytes) -> None:
        """Sends a sealed encrypted envelope."""
        sealed = SealedBox(PublicKey(recipient_public_key)).encrypt(plaintext.encode('utf-8'))
        envelope_id = _generate_ulid()
        created_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        envelope = {
            'type': 'envelope',
            'v': '0.3',
            'envelope_id': envelope_id,
            'sender_did': self.did,
            'recipient_did': recipient_did,
            'created_at': created_at,
            'ciphertext': base64url.encode(sealed),
            'content_type': 'application/json',
        }
        sig = self._signing.sign(signing_input.build(envelope)).signature
        envelope['signature'] = base64url.encode(sig)
        cost_tokens = max(1, (len(sealed) + 1023) // 1024)
        x402 = build_relay_payment(self.did, cost_tokens, envelope_id)
        ref = str(self._ref)
        self._ref += 1
        await self._send_phoenix(
            self._join_ref,
            ref,
            'relay:inbox',
            'message.send',
            {'envelope': envelope, 'payment': {'x402': x402}},
        )

    async def _send_phoenix(
        self,
        join_ref: str,
        ref: str | None,
        topic: str,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps([join_ref, ref, topic, event, payload]))

    async def _handle_phoenix(self, msg: list[Any], joined: asyncio.Event) -> None:
        event = msg[3]
        payload = msg[4] if len(msg) > 4 else {}
        if event == 'phx_reply' and payload.get('status') == 'ok':
            joined.set()
        if event == 'message.deliver':
            for handler in self._handlers:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result


def _generate_ulid() -> str:
    import secrets
    import string

    alphabet = string.digits + 'ABCDEFGHJKMNPQRSTVWXYZ'
    return ''.join(secrets.choice(alphabet) for _ in range(26))
