"""DID resolve tests."""

from plenipo.did import create_did_document, enc_public_key_from_document


def test_enc_public_key_from_document() -> None:
    result = create_did_document('agent.example.com')
    pub = enc_public_key_from_document(result.document, result.did)
    assert len(pub) == 32
