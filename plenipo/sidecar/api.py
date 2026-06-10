"""Starlette routes for the Plenipo agent sidecar."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from plenipo.discover import discover_agents
from plenipo.identity.route import declare_route, route_from_document
from plenipo.runtime import PlenipoAgentRuntime
from plenipo.sidecar.config import SidecarSecurity
from plenipo.sidecar.events import DurableEventService
from plenipo.runtime.inbox_crypto import SidecarStoreKeyError
from plenipo.sidecar.middleware import AuthMiddleware, CorsMiddleware, RequestLoggingMiddleware
from plenipo.sidecar.metrics import render_sidecar_metrics
from plenipo.sidecar.models import (
    SERVICE_NAME,
    SIDECAR_VERSION,
    build_status_payload,
    outbox_record_to_dict,
    public_route_from_identity,
    receipt_record_to_dict,
    route_record_to_dict,
    send_ack_to_dict,
)


class SidecarApp:
    """HTTP application backed by a PlenipoAgentRuntime instance."""

    def __init__(
        self,
        runtime: PlenipoAgentRuntime,
        event_buffer: DurableEventService,
        security: SidecarSecurity,
    ) -> None:
        self._runtime = runtime
        self._event_buffer = event_buffer
        self._security = security
        self._identity = runtime._identity

    def create_app(self) -> Starlette:
        """Builds the Starlette application with security middleware."""
        return Starlette(
            routes=[
                Route('/health', self.health, methods=['GET']),
                Route('/metrics', self.metrics, methods=['GET']),
                Route('/status', self.status, methods=['GET']),
                Route('/route', self.route, methods=['GET', 'POST']),
                Route('/discover', self.discover, methods=['GET']),
                Route('/send', self.send, methods=['POST']),
                Route('/events', self.events, methods=['GET']),
                Route('/events/stream', self.events_stream, methods=['GET']),
                Route('/outbox', self.outbox, methods=['GET']),
                Route('/receipts', self.receipts, methods=['GET']),
            ],
            middleware=[
                Middleware(RequestLoggingMiddleware),
                Middleware(
                    CorsMiddleware,
                    allowed_origins=self._security.allowed_origins,
                ),
                Middleware(
                    AuthMiddleware,
                    auth_enabled=self._security.auth_enabled,
                    token=self._security.token,
                    signed_request_secret=self._security.signed_request_secret,
                ),
            ],
        )

    async def health(self, _request: Request) -> JSONResponse:
        """Returns minimal process health."""
        return JSONResponse(
            {
                'ok': True,
                'service': SERVICE_NAME,
                'version': SIDECAR_VERSION,
            }
        )

    async def status(self, _request: Request) -> JSONResponse:
        """Returns sanitized runtime status."""
        identity = self._runtime._identity
        if identity is None:
            return JSONResponse({'error': 'runtime not ready'}, status_code=503)

        connected = (
            self._runtime._client is not None and self._runtime._client.connected
        )
        payload = build_status_payload(
            identity=identity,
            connected=connected,
            store=self._runtime.store,
        )
        return JSONResponse(payload)

    async def metrics(self, _request: Request) -> Response:
        """Returns sanitized local Prometheus metrics."""
        return Response(
            render_sidecar_metrics(self._runtime),
            media_type='text/plain; version=0.0.4',
        )

    async def route(self, request: Request) -> JSONResponse:
        """Returns or declares public route metadata."""
        if request.method == 'GET':
            identity = self._runtime._identity
            if identity is None:
                return JSONResponse({'error': 'runtime not ready'}, status_code=503)
            return JSONResponse(public_route_from_identity(identity))

        body = await _read_json_body(request)
        updated = await declare_route(
            protocols=_string_list(body.get('protocols')),
            capabilities=_string_list(body.get('capabilities')),
            payment=body.get('payment') if isinstance(body.get('payment'), dict) else None,
            limits=body.get('limits') if isinstance(body.get('limits'), dict) else None,
            replace=bool(body.get('replace', False)),
        )
        self._runtime._identity = updated
        self._runtime._route_declared = True
        route = route_from_document(updated.document)
        return JSONResponse(
            {
                'did': updated.did,
                'route': route,
                'core_registered': updated.core_registered,
            }
        )

    async def discover(self, request: Request) -> JSONResponse:
        """Searches registry Route Records."""
        params = request.query_params
        online_raw = params.get('online')
        online: bool | None = None
        if online_raw is not None:
            online = online_raw.lower() in ('1', 'true', 'yes')

        max_price_raw = params.get('max_price_per_kb_tokens')
        max_price = int(max_price_raw) if max_price_raw is not None else None

        limit_raw = params.get('limit', '20')
        results = await discover_agents(
            query=params.get('query'),
            capability=params.get('capability'),
            protocol=params.get('protocol'),
            payment_scheme=params.get('payment_scheme'),
            max_price_per_kb_tokens=max_price,
            online=online,
            limit=int(limit_raw),
        )
        return JSONResponse({'results': [route_record_to_dict(item) for item in results]})

    async def send(self, request: Request) -> JSONResponse:
        """Sends an encrypted paid message via the runtime."""
        body = await _read_json_body(request)
        recipient_did = body.get('recipient_did')
        message = body.get('message')
        if not isinstance(recipient_did, str) or not recipient_did:
            return JSONResponse({'error': 'recipient_did is required'}, status_code=400)
        if not isinstance(message, str):
            return JSONResponse({'error': 'message is required'}, status_code=400)

        recipient_document_url = body.get('recipient_document_url')
        envelope_id = body.get('envelope_id')
        if envelope_id is not None and not isinstance(envelope_id, str):
            return JSONResponse({'error': 'envelope_id must be a string'}, status_code=400)

        try:
            ack = await self._runtime.send(
                recipient_did,
                message,
                recipient_document_url=recipient_document_url
                if isinstance(recipient_document_url, str)
                else None,
                envelope_id=envelope_id if isinstance(envelope_id, str) else None,
            )
        except Exception as exc:
            return JSONResponse({'error': str(exc)}, status_code=502)

        return JSONResponse(send_ack_to_dict(ack))

    async def events(self, request: Request) -> JSONResponse:
        """Long-polls durable runtime events."""
        params = request.query_params
        after_id = _parse_after_id(params)
        timeout_ms = int(params.get('timeout_ms', '1000'))
        limit = int(params.get('limit', '100'))
        include_plaintext = _parse_bool(params.get('include_plaintext'), default=True)

        try:
            events, next_after_id = await self._event_buffer.wait_for_events(
                after_id=after_id,
                timeout_ms=max(0, min(timeout_ms, 60_000)),
                limit=max(1, min(limit, 100)),
                include_plaintext=include_plaintext,
            )
        except SidecarStoreKeyError as exc:
            return JSONResponse({'error': str(exc)}, status_code=500)

        return JSONResponse(
            {
                'events': events,
                'next_after_id': next_after_id,
                'since_id': next_after_id,
            }
        )

    async def events_stream(self, request: Request) -> StreamingResponse:
        """Streams durable events over Server-Sent Events."""
        params = request.query_params
        after_id = _parse_after_id(params, request.headers.get('last-event-id'))
        include_plaintext = _parse_bool(params.get('include_plaintext'), default=True)

        async def event_generator():
            cursor = after_id
            while True:
                if await request.is_disconnected():
                    break
                try:
                    events, cursor = self._event_buffer.list_events_after(
                        after_id=cursor,
                        limit=50,
                        include_plaintext=include_plaintext,
                    )
                except SidecarStoreKeyError as exc:
                    yield f'event: error\ndata: {json.dumps({"error": str(exc)})}\n\n'
                    break

                if not events:
                    await asyncio.sleep(0.5)
                    continue

                for event in events:
                    event_id = event.get('id', cursor)
                    event_type = event.get('type', 'event')
                    yield (
                        f'id: {event_id}\n'
                        f'event: {event_type}\n'
                        f'data: {json.dumps(event, separators=(",", ":"))}\n\n'
                    )
                await asyncio.sleep(0.1)

        return StreamingResponse(event_generator(), media_type='text/event-stream')

    async def outbox(self, request: Request) -> JSONResponse:
        """Returns sanitized outbox rows."""
        params = request.query_params
        status = params.get('status')
        limit = int(params.get('limit', '100'))
        rows = self._runtime.outbox(
            status=status if isinstance(status, str) else None,
            limit=max(1, min(limit, 500)),
        )
        return JSONResponse({'outbox': [outbox_record_to_dict(row) for row in rows]})

    async def receipts(self, request: Request) -> JSONResponse:
        """Returns sanitized receipt rows."""
        params = request.query_params
        limit = int(params.get('limit', '100'))
        rows = self._runtime.receipts(limit=max(1, min(limit, 500)))
        return JSONResponse({'receipts': [receipt_record_to_dict(row) for row in rows]})


async def _read_json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return {}
    if isinstance(body, dict):
        return body
    return {}


def _parse_after_id(params: Any, last_event_id: str | None = None) -> int:
    if last_event_id:
        try:
            return int(last_event_id)
        except ValueError:
            pass
    if params.get('after_id') is not None:
        return int(params.get('after_id', '0'))
    return int(params.get('since_id', '0'))


def _parse_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in ('1', 'true', 'yes')


def _string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return None
