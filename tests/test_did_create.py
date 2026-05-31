"""Tests for DID document creation."""

from plenipo.did import create_did_document


def test_create_did_document_structure() -> None:
    result = create_did_document('agent.example.com')
    assert result.did == 'did:web:agent.example.com'
    assert len(result.document['verificationMethod']) == 2
    assert result.document['service'][0]['type'] == 'PlenipoAgent'
