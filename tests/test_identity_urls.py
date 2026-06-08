"""Tests for Core-hosted identity URL helpers."""

from __future__ import annotations

from plenipo.identity.urls import core_hosted_document_url


def test_core_hosted_document_url_encodes_did() -> None:
    did = 'did:web:localhost:agents:abc123'
    url = core_hosted_document_url('http://localhost:4000', did)
    assert url == 'http://localhost:4000/v1/dids/did%3Aweb%3Alocalhost%3Aagents%3Aabc123'


def test_core_hosted_document_url_strips_trailing_slash() -> None:
    did = 'did:web:localhost:agents:test'
    url = core_hosted_document_url('http://localhost:4000/', did)
    assert url.startswith('http://localhost:4000/v1/dids/')
