"""DID generation and management."""

from plenipo.did.create import DidCreateResult, create_did_document
from plenipo.did.resolve import enc_public_key_from_document, resolve_enc_public_key

__all__ = [
    'DidCreateResult',
    'create_did_document',
    'enc_public_key_from_document',
    'resolve_enc_public_key',
]
