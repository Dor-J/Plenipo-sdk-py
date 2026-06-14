"""Machine-readable Plenipo error helpers for SDK clients and CLIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_DOCS_BASE = 'https://plenipo.dev/errors'


@dataclass(frozen=True)
class StructuredErrorBody:
    """Public structured error wire shape."""

    code: str
    message: str
    docs_url: str
    v: str = '1.0'
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes to JSON-compatible mapping."""
        payload: dict[str, Any] = {
            'code': self.code,
            'message': self.message,
            'docs_url': self.docs_url,
            'v': self.v,
        }
        if self.details is not None:
            payload['details'] = self.details
        return payload


class PlenipoStructuredError(Exception):
    """Error with machine-readable fields agents can act on."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        docs_url: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.docs_url = docs_url
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Serializes to the public wire shape."""
        return StructuredErrorBody(
            code=self.code,
            message=str(self),
            docs_url=self.docs_url,
            details=self.details,
        ).to_dict()


def docs_url_for_code(code: str, docs_base: str = DEFAULT_DOCS_BASE) -> str:
    """Builds a docs anchor URL for a public error code."""
    return f'{docs_base}#{code}'


def parse_structured_error_body(
    body: Any,
    *,
    fallback_code: str,
    fallback_message: str,
) -> StructuredErrorBody:
    """Parses an HTTP error response body into a structured error when possible."""
    if not isinstance(body, dict):
        return StructuredErrorBody(
            code=fallback_code,
            message=fallback_message,
            docs_url=docs_url_for_code(fallback_code),
        )

    code = body.get('code') if isinstance(body.get('code'), str) else fallback_code
    message = body.get('message')
    if not isinstance(message, str):
        error = body.get('error')
        message = error if isinstance(error, str) else fallback_message
    docs_url = body.get('docs_url')
    if not isinstance(docs_url, str):
        docs_url = docs_url_for_code(code)
    version = body.get('v')
    return StructuredErrorBody(
        code=code,
        message=message,
        docs_url=docs_url,
        v=version if isinstance(version, str) else '1.0',
    )


def format_structured_error(error: BaseException | Any) -> dict[str, Any]:
    """Normalizes any exception to a structured error body."""
    if isinstance(error, PlenipoStructuredError):
        return error.to_dict()
    if isinstance(error, Exception):
        return StructuredErrorBody(
            code='INTERNAL_ERROR',
            message=str(error),
            docs_url=docs_url_for_code('INTERNAL_ERROR'),
        ).to_dict()
    return StructuredErrorBody(
        code='INTERNAL_ERROR',
        message=str(error),
        docs_url=docs_url_for_code('INTERNAL_ERROR'),
    ).to_dict()
