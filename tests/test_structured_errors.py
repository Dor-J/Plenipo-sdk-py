"""Tests for structured SDK errors."""

from __future__ import annotations

from plenipo.errors.structured import (
    PlenipoStructuredError,
    docs_url_for_code,
    format_structured_error,
    parse_structured_error_body,
)


def test_docs_url_for_code() -> None:
    assert docs_url_for_code('INSUFFICIENT_BALANCE') == (
        'https://plenipo.dev/errors#INSUFFICIENT_BALANCE'
    )


def test_parse_structured_error_body() -> None:
    body = parse_structured_error_body(
        {
            'code': 'RATE_LIMITED',
            'message': 'Rate limit exceeded.',
            'docs_url': 'https://plenipo.dev/errors#RATE_LIMITED',
        },
        fallback_code='INTERNAL_ERROR',
        fallback_message='fallback',
    )
    assert body.code == 'RATE_LIMITED'
    assert body.docs_url.endswith('#RATE_LIMITED')


def test_format_structured_error() -> None:
    error = PlenipoStructuredError(
        code='PING_TIMEOUT',
        message='timed out',
        docs_url='https://plenipo.dev/errors#PING_TIMEOUT',
    )
    payload = format_structured_error(error)
    assert payload['code'] == 'PING_TIMEOUT'
    assert payload['docs_url'].endswith('#PING_TIMEOUT')
