"""Tests for DID document creation."""

from plenipo.did import create_did_document


def test_create_did_document_structure() -> None:
    result = create_did_document('agent.example.com')
    assert result.did == 'did:web:agent.example.com'
    assert result.document_url == 'https://agent.example.com/.well-known/did.json'
    assert len(result.document['verificationMethod']) == 2
    service = result.document['service'][0]
    assert service['type'] == 'PlenipoAgent'
    assert service['protocols'] == ['plenipo.message.v1']
    assert service['payment'] == {
        'model': 'per_kb',
        'price_per_kb_tokens': 1,
        'accepted_schemes': ['plenipo-prepaid-token'],
    }
    assert service['limits'] == {
        'max_message_kb': 256,
        'offline_queue_ttl_seconds': 86400,
    }
    assert service['encryption'] == {
        'alg': 'x25519-xsalsa20poly1305',
        'publicKeyRef': '#enc-key',
    }


def test_create_path_based_did_document() -> None:
    result = create_did_document('agents.example.com', path_segments=['local', 'python-a'])
    assert result.did == 'did:web:agents.example.com:local:python-a'
    assert result.document_url == 'https://agents.example.com/local/python-a/did.json'
    assert result.document['id'] == result.did
