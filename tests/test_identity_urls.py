"""Tests for Core-hosted identity URL helpers."""

from __future__ import annotations

import pytest

from plenipo.identity.urls import (
    core_hosted_document_url,
    external_did_web_document_url,
    is_core_hosted_local_did,
    validate_production_did_web,
)


def test_core_hosted_document_url_uses_query_param() -> None:
    did = 'did:web:localhost:agents:abc123'
    url = core_hosted_document_url('http://localhost:4000', did)
    assert url == 'http://localhost:4000/v1/dids?did=did%3Aweb%3Alocalhost%3Aagents%3Aabc123'


def test_core_hosted_document_url_strips_trailing_slash() -> None:
    did = 'did:web:localhost:agents:test'
    url = core_hosted_document_url('http://localhost:4000/', did)
    assert url.startswith('http://localhost:4000/v1/dids?did=')


def test_external_did_web_document_url() -> None:
    assert external_did_web_document_url('did:web:agent.example.com') == (
        'https://agent.example.com/.well-known/did.json'
    )
    assert external_did_web_document_url('did:web:agents.example.com:local:python-a') == (
        'https://agents.example.com/local/python-a/did.json'
    )


def test_validate_production_did_web() -> None:
    validate_production_did_web(
        'did:web:agents.example.com:local:python-a',
        'https://agents.example.com/local/python-a/did.json',
    )

    with pytest.raises(ValueError, match='https'):
        validate_production_did_web(
            'did:web:agent.example.com',
            'http://agent.example.com/.well-known/did.json',
        )

    with pytest.raises(ValueError, match='DID document URL'):
        validate_production_did_web(
            'did:web:agent.example.com',
            'https://other.example.com/.well-known/did.json',
        )


def test_core_hosted_local_did_detection() -> None:
    assert is_core_hosted_local_did('did:web:localhost:agents:abc')
    assert not is_core_hosted_local_did('did:web:agent.example.com')
