"""Relay WebSocket connect URL builder (Python/TypeScript parity)."""

from __future__ import annotations

from urllib.parse import quote

PHOENIX_VSN = '2.0.0'


def relay_ws_base_url(relay_url: str) -> str:
    """Strips query params from a relay WebSocket base URL."""
    return relay_url.split('?', 1)[0]


def build_relay_connect_url(
    relay_url: str,
    *,
    did: str,
    nonce: str,
    signature: str,
    did_document_url: str,
) -> str:
    """
    Builds a relay WebSocket URL with auth query params.

    Param order matches TypeScript SDK and Core cluster tests (`vsn` last).
    """
    base = relay_ws_base_url(relay_url)
    query = '&'.join(
        [
            f'did={quote(did, safe="")}',
            f'nonce={quote(nonce, safe="")}',
            f'signature={quote(signature, safe="")}',
            f'did_document_url={quote(did_document_url, safe="")}',
            f'vsn={PHOENIX_VSN}',
        ]
    )
    return f'{base}?{query}'


def build_relay_connect_url_vsn_first(
    relay_url: str,
    *,
    did: str,
    nonce: str,
    signature: str,
    did_document_url: str,
) -> str:
    """Builds the alternate client shape with `vsn` first (regression coverage)."""
    base = relay_ws_base_url(relay_url)
    query = '&'.join(
        [
            f'vsn={PHOENIX_VSN}',
            f'did={quote(did, safe="")}',
            f'nonce={quote(nonce, safe="")}',
            f'signature={quote(signature, safe="")}',
            f'did_document_url={quote(did_document_url, safe="")}',
        ]
    )
    return f'{base}?{query}'


def relay_connect_debug_meta(
    relay_url: str,
    *,
    did: str,
    nonce: str,
    signature: str,
    did_document_url: str,
) -> dict[str, object]:
    """Sanitized debug metadata for relay WebSocket connects."""
    return {
        'relay_url': relay_ws_base_url(relay_url),
        'did': did,
        'did_document_url': did_document_url,
        'encoded_query_keys': ['did', 'nonce', 'signature', 'did_document_url', 'vsn'],
        'final_ws_url': _redact_signature(
            build_relay_connect_url(
                relay_url,
                did=did,
                nonce=nonce,
                signature=signature,
                did_document_url=did_document_url,
            )
        ),
    }


def _redact_signature(url: str) -> str:
    marker = 'signature='
    start = url.find(marker)
    if start < 0:
        return url
    end = url.find('&', start)
    if end < 0:
        return url[: start + len(marker)] + '<redacted>'
    return url[: start + len(marker)] + '<redacted>' + url[end:]
