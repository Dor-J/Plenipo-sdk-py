"""Starlette routes for the Plenipo agent sidecar."""

from __future__ import annotations

import json
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from plenipo.discover import discover_agents
from plenipo.identity.route import declare_route, route_from_document
from plenipo.runtime import PlenipoAgentRuntime
from plenipo.sidecar.events import EventBuffer
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

    def __init__(self, runtime: PlenipoAgentRuntime, event_buffer: EventBuffer) -> None:
        self._runtime = runtime
        self._event_buffer = event_buffer
        self._identity = runtime._identity

    def create_app(self) -> Starlette:
        """Builds the Starlette application."""
        return Starlette(
            routes=[
                Route('/health', self.health, methods=['GET']),
                Route('/status', self.status, methods=['GET']),
                Route('/route', self.route, methods=['GET', 'POST']),
                Route('/discover', self.discover, methods=['GET']),
                Route('/send', self.send, methods=['POST']),
                Route('/events', self.events, methods=['GET']),
                Route('/outbox', self.outbox, methods=['GET']),
                Route('/receipts', self.receipts, methods=['GET']),
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
        """Long-polls buffered runtime events."""
        params = request.query_params
        since_id = int(params.get('since_id', '0'))
        timeout_ms = int(params.get('timeout_ms', '30000'))
        limit = int(params.get('limit', '50'))

        matches = await self._event_buffer.wait_for_events(
            since_id=since_id,
            timeout_ms=max(0, min(timeout_ms, 60_000)),
            limit=max(1, min(limit, 100)),
        )
        events = [item.payload for item in matches]
        next_since_id = matches[-1].event_id if matches else since_id
        return JSONResponse({'events': events, 'since_id': next_since_id})

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


def _string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return None
