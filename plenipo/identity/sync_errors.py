"""Maps Core registration failures to user-facing sync warnings."""

from __future__ import annotations

import httpx


def sync_warnings_from_error(exc: Exception) -> list[str]:
    """Returns actionable warnings for a failed Core sync attempt."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 403:
            return ['Core-hosted local registration is disabled on Core']
        if status in (400, 401):
            return [f'Core registration rejected (HTTP {status})']
        if status == 409:
            return ['Core rejected auth key change (key takeover)']
        return [f'Core registration failed (HTTP {status})']

    if isinstance(exc, (httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError)):
        return ['Core unavailable']

    return ['Core registration failed']
