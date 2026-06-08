"""Sync error mapping tests."""

from __future__ import annotations

import httpx

from plenipo.identity.sync_errors import sync_warnings_from_error


def test_sync_warnings_maps_403() -> None:
    request = httpx.Request('POST', 'http://localhost:4000/v1/dids')
    response = httpx.Response(403, request=request)
    exc = httpx.HTTPStatusError('forbidden', request=request, response=response)
    assert sync_warnings_from_error(exc) == [
        'Core-hosted local registration is disabled on Core'
    ]


def test_sync_warnings_maps_network_error() -> None:
    request = httpx.Request('GET', 'http://127.0.0.1:1/health')
    exc = httpx.ConnectError('connection refused', request=request)
    assert sync_warnings_from_error(exc) == ['Core unavailable']
