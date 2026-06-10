"""Registry discovery client."""

from __future__ import annotations

import os

import httpx

from plenipo.discover.records import RouteRecord, normalize_route_record


async def discover_agents(
    *,
    query: str | None = None,
    capability: str | None = None,
    protocol: str | None = None,
    payment_scheme: str | None = None,
    max_price_per_kb_tokens: int | None = None,
    online: bool | None = None,
    limit: int = 20,
    registry_url: str | None = None,
) -> list[RouteRecord]:
    """Searches the Plenipo DID registry and returns Route Records."""
    base = registry_url or os.environ.get('PLENIPO_REGISTRY_URL', 'http://localhost:4001')
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

    async with httpx.AsyncClient() as client:
        response = await client.get(f'{base}/api/v1/search', params=params)
        response.raise_for_status()
        body = response.json()
        results = list(body.get('results', []))
        return [normalize_route_record(item) for item in results if isinstance(item, dict)]
