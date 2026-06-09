"""WebSocket relay client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict, cast
from urllib.parse import quote, urlparse

import httpx
import websockets
from nacl.public import PublicKey, SealedBox
from nacl.signing import SigningKey

from plenipo.crypto import base64url, signing_input
from plenipo.delivery import build_receipt
from plenipo.payments import build_relay_payment

MessageHandler = Callable[[dict[str, Any]], Awaitable[None] | None]
ReceiptHandler = Callable[[dict[str, Any]], Awaitable[None] | None]

SendAckStatus = Literal['delivered', 'queued']


class SendAck(TypedDict, total=False):
    """Ack response from message.send."""

    type: str
    v: str
    envelope_id: str
    status: SendAckStatus
    queued_until: str
    bytes: int
    balance: int
    ciphertext_bytes: int
    billable_kb: int
    charged_tokens: int
    balance_after: int


class PlenipoClient:
    """Programmatic client for the Plenipo relay."""

    def __init__(
        self,
        *,
        did: str,
        auth_secret_b64: str,
        did_document_url: str,
        relay_url: str = 'ws://localhost:4000/agent/websocket',
        auto_receipt: bool = True,
        protocol_version: str = '1.0',
    ) -> None:
        self.did = did
        self._signing = SigningKey(base64url.decode(auth_secret_b64))
        self.did_document_url = did_document_url
        self._auto_receipt = auto_receipt
        self._protocol_version = protocol_version
        parsed = urlparse(relay_url.replace('ws://', 'http://').replace('wss://', 'https://'))
        self.relay_http_url = f'{parsed.scheme}://{parsed.netloc}'
        self._ws_url = relay_url
        self._handlers: list[MessageHandler] = []
        self._receipt_handlers: list[ReceiptHandler] = []
        self._ws: Any = None
        self._join_ref = '1'
        self._ref = 2
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._connected = False

    def on_message(self, handler: MessageHandler) -> None:
        """Registers a handler for incoming envelopes."""
        self._handlers.append(handler)

    def on_receipt(self, handler: ReceiptHandler) -> None:
        """Registers a handler for message.receipt pushes to the sender."""
        self._receipt_handlers.append(handler)

    async def connect(self) -> None:
        """Authenticates and joins relay:inbox."""
        async with httpx.AsyncClient() as client:
            challenge = (
                await client.post(
                    f'{self.relay_http_url}/auth/challenge',
                    json={'did': self.did},
                )
            ).json()

        nonce = challenge['nonce']
        signature = self._signing.sign(base64url.decode(nonce)).signature
        query = '&'.join(
            [
                f'did={quote(self.did, safe="")}',
                f'nonce={quote(nonce, safe="")}',
                f'signature={quote(base64url.encode(signature), safe="")}',
                f'did_document_url={quote(self.did_document_url, safe="")}',
                'vsn=2.0.0',
            ]
        )
        ws_target = f'{self._ws_url}?{query}'
        self._ws = await websockets.connect(ws_target)
        await self._send_phoenix(self._join_ref, None, 'relay:inbox', 'phx_join', {})
        joined = asyncio.Event()

        async def reader() -> None:
            assert self._ws is not None
            async for raw in self._ws:
                msg = json.loads(raw)
                await self._handle_phoenix(msg, joined)

        self._reader_task = asyncio.create_task(reader())
        await joined.wait()
        self._connected = True

    async def disconnect(self) -> None:
        """Closes the relay WebSocket and stops the reader task."""
        self._connected = False
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError('relay disconnected'))
        self._pending.clear()

    @property
    def connected(self) -> bool:
        """Whether the relay WebSocket is connected."""
        return self._connected

    async def send(
        self,
        recipient_did: str,
        plaintext: str,
        recipient_public_key: bytes,
    ) -> SendAck:
        """Sends a sealed encrypted envelope and returns the relay ack."""
        sealed = SealedBox(PublicKey(recipient_public_key)).encrypt(plaintext.encode('utf-8'))
        envelope_id = _generate_ulid()
        created_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        envelope = {
            'type': 'envelope',
            'v': self._protocol_version,
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
        ack = await self._request_reply(
            ref,
            'message.send',
            {'envelope': envelope, 'payment': {'x402': x402}},
        )
        return cast(SendAck, ack)

    async def send_receipt(self, envelope_id: str) -> dict[str, Any]:
        """Sends a delivery receipt for a received envelope."""
        ref = str(self._ref)
        self._ref += 1
        return cast(
            dict[str, Any],
            await self._request_reply(ref, 'message.receipt', build_receipt(envelope_id)),
        )

    async def get_delivery_status(self, envelope_id: str) -> dict[str, Any]:
        """Queries delivery status via the relay channel."""
        ref = str(self._ref)
        self._ref += 1
        return cast(
            dict[str, Any],
            await self._request_reply(
                ref,
                'delivery.get',
                {'envelope_id': envelope_id},
            ),
        )

    async def get_balance(self) -> int:
        """Queries current token balance via the relay channel."""
        ref = str(self._ref)
        self._ref += 1
        payload = cast(dict[str, Any], await self._request_reply(ref, 'balance.get', {}))
        return int(payload['balance'])

    async def list_receipts(
        self,
        *,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Lists persisted delivery receipts for the authenticated sender."""
        request: dict[str, Any] = {'limit': limit}
        if since:
            request['since'] = since
        ref = str(self._ref)
        self._ref += 1
        payload = cast(
            dict[str, Any],
            await self._request_reply(ref, 'receipt.list', request),
        )
        receipts = payload.get('receipts', [])
        if not isinstance(receipts, list):
            return []
        return [cast(dict[str, Any], row) for row in receipts]

    async def _request_reply(self, ref: str, event: str, payload: dict[str, Any]) -> Any:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[ref] = fut
        await self._send_phoenix(self._join_ref, ref, 'relay:inbox', event, payload)
        return await fut

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
        ref = msg[1] if len(msg) > 1 else None

        if event == 'phx_reply':
            if ref and ref in self._pending:
                pending = self._pending.pop(ref)
                if payload.get('status') == 'ok':
                    pending.set_result(payload.get('response', {}))
                else:
                    pending.set_exception(RuntimeError(str(payload)))
            elif payload.get('status') == 'ok' and not payload.get('response'):
                joined.set()

        if event == 'message.deliver':
            for handler in self._handlers:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result
            if self._auto_receipt and payload.get('envelope_id'):
                await self.send_receipt(payload['envelope_id'])

        if event == 'message.receipt':
            for handler in self._receipt_handlers:
                result = handler(payload)
                if asyncio.iscoroutine(result):
                    await result


def _generate_ulid() -> str:
    import secrets
    import string

    alphabet = string.digits + 'ABCDEFGHJKMNPQRSTVWXYZ'
    return ''.join(secrets.choice(alphabet) for _ in range(26))
