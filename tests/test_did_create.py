"""Tests for DID document creation."""

from plenipo.did import create_did_document


def test_create_did_document_structure() -> None:
    result = create_did_document('agent.example.com')
    assert result.did == 'did:web:agent.example.com'
    assert result.document_url == 'https://agent.example.com/.well-known/did.json'
    assert len(result.document['verificationMethod']) == 2
    assert result.document['service'][0]['type'] == 'PlenipoAgent'


def test_create_path_based_did_document() -> None:
    result = create_did_document('agents.example.com', path_segments=['local', 'python-a'])
    assert result.did == 'did:web:agents.example.com:local:python-a'
    assert result.document_url == 'https://agents.example.com/local/python-a/did.json'
    assert result.document['id'] == result.did
