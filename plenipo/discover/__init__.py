"""Registry discovery client."""

from __future__ import annotations

import os
from typing import Any

import httpx


async def discover_agents(
    *,
    query: str | None = None,
    capability: str | None = None,
    limit: int = 20,
    registry_url: str | None = None,
) -> list[dict[str, Any]]:
    """Searches the Plenipo DID registry."""
    base = registry_url or os.environ.get('PLENIPO_REGISTRY_URL', 'http://localhost:4001')
    params: dict[str, str | int] = {'limit': limit}
    if query:
        params['query'] = query
    if capability:
        params['capability'] = capability

    async with httpx.AsyncClient() as client:
        response = await client.get(f'{base}/api/v1/search', params=params)
        response.raise_for_status()
        body = response.json()
        return list(body.get('results', []))
