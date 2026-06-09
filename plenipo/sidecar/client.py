"""HTTP client for the Plenipo agent sidecar local API."""

from __future__ import annotations

import os
from typing import Any

import httpx

from plenipo.sidecar.auth import read_sidecar_token_file


class SidecarClientError(Exception):
    """Raised when a sidecar HTTP request fails."""


class PlenipoSidecarClient:
    """Synchronous client for the local Plenipo sidecar HTTP API."""

    def __init__(
        self,
        base_url: str = 'http://127.0.0.1:8787',
        *,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip('/')
        self._token = token
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self._auth_headers(),
            timeout=self._timeout,
        )

    @classmethod
    def from_env(cls) -> PlenipoSidecarClient:
        """Creates a client from PLENIPO_SIDECAR_URL and token env/file."""
        base_url = os.environ.get('PLENIPO_SIDECAR_URL', 'http://127.0.0.1:8787')
        token = os.environ.get('PLENIPO_SIDECAR_TOKEN') or read_sidecar_token_file()
        return cls(base_url=base_url, token=token)

    def close(self) -> None:
        """Closes the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> PlenipoSidecarClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        """Returns sidecar health without authentication."""
        return self._request('GET', '/health', auth=False)

    def status(self) -> dict[str, Any]:
        """Returns sanitized runtime status."""
        return self._request('GET', '/status')

    def route(self) -> dict[str, Any]:
        """Returns public route metadata."""
        return self._request('GET', '/route')

    def declare_route(self, route: dict[str, Any]) -> dict[str, Any]:
        """Declares or updates route metadata."""
        return self._request('POST', '/route', json_body=route)

    def discover(
        self,
        *,
        query: str | None = None,
        capability: str | None = None,
        protocol: str | None = None,
        payment_scheme: str | None = None,
        max_price_per_kb_tokens: int | None = None,
        online: bool | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Searches registry Route Records."""
        params: dict[str, str | int] = {'limit': limit}
        if query:
            params['query'] = query
        if capability:
            params['capability'] = capability
        if protocol:
            params['protocol'] = protocol
        if payment_scheme:
            params['payment_scheme'] = payment_scheme
        if max_price_per_kb_tokens is not None:
            params['max_price_per_kb_tokens'] = max_price_per_kb_tokens
        if online is True:
            params['online'] = 'true'
        return self._request('GET', '/discover', params=params)

    def send(
        self,
        recipient_did: str,
        message: str,
        *,
        recipient_document_url: str | None = None,
        envelope_id: str | None = None,
    ) -> dict[str, Any]:
        """Sends an encrypted paid message."""
        body: dict[str, Any] = {
            'recipient_did': recipient_did,
            'message': message,
        }
        if recipient_document_url is not None:
            body['recipient_document_url'] = recipient_document_url
        if envelope_id is not None:
            body['envelope_id'] = envelope_id
        return self._request('POST', '/send', json_body=body)

    def events(
        self,
        *,
        after_id: int = 0,
        since_id: int | None = None,
        timeout_ms: int = 1000,
        limit: int = 100,
        include_plaintext: bool = True,
    ) -> dict[str, Any]:
        """Long-polls durable runtime events."""
        cursor = after_id if since_id is None else since_id
        return self._request(
            'GET',
            '/events',
            params={
                'after_id': cursor,
                'timeout_ms': timeout_ms,
                'limit': limit,
                'include_plaintext': str(include_plaintext).lower(),
            },
            timeout=max(self._timeout, (timeout_ms / 1000.0) + 5.0),
        )

    def stream_events(
        self,
        *,
        after_id: int = 0,
        include_plaintext: bool = True,
    ):
        """Yields durable events from the SSE stream."""
        headers = self._auth_headers()
        headers['Accept'] = 'text/event-stream'
        params = {
            'after_id': after_id,
            'include_plaintext': str(include_plaintext).lower(),
        }
        with self._client.stream(
            'GET',
            '/events/stream',
            params=params,
            headers=headers,
            timeout=None,
        ) as response:
            if response.status_code >= 400:
                raise SidecarClientError(
                    f'GET /events/stream failed with {response.status_code}: {response.text}'
                )
            event_id = after_id
            event_type = 'message'
            data_lines: list[str] = []
            for line in response.iter_lines():
                if line is None:
                    continue
                if line == '':
                    if data_lines:
                        import json

                        payload = json.loads('\n'.join(data_lines))
                        yield payload
                    data_lines = []
                    continue
                if line.startswith('id:'):
                    event_id = int(line.split(':', 1)[1].strip())
                elif line.startswith('event:'):
                    event_type = line.split(':', 1)[1].strip()
                elif line.startswith('data:'):
                    data_lines.append(line.split(':', 1)[1].strip())
            _ = (event_id, event_type)

    def outbox(self, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
        """Returns sanitized outbox rows."""
        params: dict[str, str | int] = {'limit': limit}
        if status:
            params['status'] = status
        return self._request('GET', '/outbox', params=params)

    def receipts(self, *, limit: int = 100) -> dict[str, Any]:
        """Returns sanitized receipt rows."""
        return self._request('GET', '/receipts', params={'limit': limit})

    def _auth_headers(self) -> dict[str, str]:
        if self._token:
            return {'Authorization': f'Bearer {self._token}'}
        return {}

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        headers = self._auth_headers() if auth else {}
        response = self._client.request(
            method,
            path,
            params=params,
            json=json_body,
            headers=headers,
            timeout=timeout or self._timeout,
        )
        if response.status_code >= 400:
            raise SidecarClientError(
                f'{method} {path} failed with {response.status_code}: {response.text}'
            )
        body = response.json()
        if isinstance(body, dict):
            return body
        raise SidecarClientError(f'{method} {path} returned non-object JSON')
