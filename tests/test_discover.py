"""Registry discovery client tests."""

from __future__ import annotations

from typing import Any

import pytest

from plenipo.discover import discover_agents


class FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')

    def json(self) -> dict[str, Any]:
        return self._body


class FakeAsyncClient:
    calls: list[tuple[str, dict[str, str | int]]] = []
    response = FakeResponse({'results': [{'did': 'did:web:agent.local'}]})

    async def __aenter__(self) -> 'FakeAsyncClient':
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    async def get(self, url: str, *, params: dict[str, str | int]) -> FakeResponse:
        self.calls.append((url, params))
        return self.response


@pytest.fixture(autouse=True)
def reset_fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAsyncClient.calls = []
    FakeAsyncClient.response = FakeResponse({'results': [{'did': 'did:web:agent.local'}]})
    monkeypatch.setattr('httpx.AsyncClient', FakeAsyncClient)


async def test_discover_agents_sends_query_params() -> None:
    results = await discover_agents(
        query='agent',
        capability='messaging',
        limit=5,
        registry_url='https://registry.example',
    )

    assert results == [{'did': 'did:web:agent.local'}]
    assert FakeAsyncClient.calls == [
        (
            'https://registry.example/api/v1/search',
            {'limit': 5, 'query': 'agent', 'capability': 'messaging'},
        )
    ]


async def test_discover_agents_raises_on_http_error() -> None:
    FakeAsyncClient.response = FakeResponse({'error': 'down'}, status_code=503)

    with pytest.raises(RuntimeError, match='HTTP 503'):
        await discover_agents(registry_url='https://registry.example')
