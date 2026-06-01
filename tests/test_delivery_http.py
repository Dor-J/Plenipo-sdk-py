"""Delivery HTTP helper tests."""

from __future__ import annotations

from typing import Any

import pytest

from plenipo.delivery import get_delivery_status


class Response:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')

    def json(self) -> dict[str, Any]:
        return self._body


class Client:
    response = Response({'status': 'delivered'})
    urls: list[str] = []

    async def __aenter__(self) -> 'Client':
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get(self, url: str) -> Response:
        self.urls.append(url)
        return self.response


@pytest.fixture(autouse=True)
def patch_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    Client.response = Response({'status': 'delivered'})
    Client.urls = []
    monkeypatch.setattr('httpx.AsyncClient', Client)


async def test_get_delivery_status_success() -> None:
    assert await get_delivery_status('https://relay.example', '01JENV') == {'status': 'delivered'}
    assert Client.urls == ['https://relay.example/v1/delivery/01JENV']


async def test_get_delivery_status_raises_on_error() -> None:
    Client.response = Response({'error': 'missing'}, status_code=404)

    with pytest.raises(RuntimeError, match='HTTP 404'):
        await get_delivery_status('https://relay.example', '01JENV')
