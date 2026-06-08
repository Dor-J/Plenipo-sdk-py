"""URL helpers for Core-hosted local identities."""

from __future__ import annotations

from urllib.parse import quote


def core_hosted_document_url(core_url: str, did: str) -> str:
    """Returns the Core resolver URL for a Core-hosted DID document."""
    encoded_did = quote(did, safe='')
    return f'{core_url.rstrip("/")}/v1/dids?did={encoded_did}'
