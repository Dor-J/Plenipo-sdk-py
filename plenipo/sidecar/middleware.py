"""Sidecar HTTP middleware for auth, CORS, and sanitized request logging."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from plenipo.sidecar.auth import constant_time_token_match

logger = logging.getLogger('plenipo.sidecar.access')

CallNext = Callable[[Request], Awaitable[Response]]

PUBLIC_PATHS = frozenset({'/health'})
SIGNATURE_MAX_AGE_SECONDS = 300


class AuthMiddleware(BaseHTTPMiddleware):
    """Requires bearer token on all endpoints except /health."""

    def __init__(
        self,
        app: object,
        *,
        auth_enabled: bool,
        token: str | None,
        signed_request_secret: str | None = None,
    ) -> None:
        super().__init__(app)
        self._auth_enabled = auth_enabled
        self._token = token
        self._signed_request_secret = signed_request_secret

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        if not self._auth_enabled or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        if self._token is None:
            return JSONResponse({'error': 'unauthorized'}, status_code=401)

        auth_header = request.headers.get('authorization', '')
        if not auth_header.lower().startswith('bearer '):
            return JSONResponse({'error': 'unauthorized'}, status_code=401)

        provided = auth_header[7:].strip()
        if not provided or not constant_time_token_match(provided, self._token):
            return JSONResponse({'error': 'unauthorized'}, status_code=401)

        if self._signed_request_secret and not await _verify_signed_request(
            request,
            self._signed_request_secret,
        ):
            return JSONResponse({'error': 'unauthorized'}, status_code=401)

        return await call_next(request)


class CorsMiddleware(BaseHTTPMiddleware):
    """Rejects browser Origin headers unless explicitly allowed."""

    def __init__(self, app: object, *, allowed_origins: frozenset[str]) -> None:
        super().__init__(app)
        self._allowed_origins = allowed_origins

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        origin = request.headers.get('origin')
        if origin and origin not in self._allowed_origins:
            return JSONResponse({'error': 'origin not allowed'}, status_code=403)

        if request.method == 'OPTIONS' and origin and origin in self._allowed_origins:
            return Response(status_code=204, headers=_cors_headers(origin))

        response = await call_next(request)
        if origin and origin in self._allowed_origins:
            for key, value in _cors_headers(origin).items():
                response.headers[key] = value
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status, and duration without request bodies."""

    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            '%s %s %s duration_ms=%d',
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


def _cors_headers(origin: str) -> dict[str, str]:
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': (
            'Authorization, Content-Type, X-Plenipo-Timestamp, X-Plenipo-Signature'
        ),
        'Access-Control-Max-Age': '600',
        'Vary': 'Origin',
    }


def build_signed_request_headers(
    secret: str,
    method: str,
    path: str,
    body: bytes | str = b'',
    *,
    timestamp: str | None = None,
) -> dict[str, str]:
    """Builds sidecar signed-request headers for tests and custom clients."""
    timestamp = timestamp or str(int(time.time()))
    body_bytes = body.encode() if isinstance(body, str) else body
    digest = hashlib.sha256(body_bytes).hexdigest()
    signature = _sign(secret, method, path, timestamp, digest)
    return {
        'X-Plenipo-Timestamp': timestamp,
        'X-Plenipo-Signature': signature,
    }


async def _verify_signed_request(request: Request, secret: str) -> bool:
    timestamp = request.headers.get('x-plenipo-timestamp')
    signature = request.headers.get('x-plenipo-signature')
    if not timestamp or not signature:
        return False

    try:
        timestamp_seconds = int(timestamp)
    except ValueError:
        return False

    if abs(int(time.time()) - timestamp_seconds) > SIGNATURE_MAX_AGE_SECONDS:
        return False

    body = await request.body()
    digest = hashlib.sha256(body).hexdigest()
    expected = _sign(secret, request.method, request.url.path, timestamp, digest)
    return hmac.compare_digest(signature, expected)


def _sign(secret: str, method: str, path: str, timestamp: str, digest: str) -> str:
    payload = '\n'.join([method.upper(), path, timestamp, digest])
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
