"""Base64url encoding without padding."""

import base64


def encode(data: bytes) -> str:
    """Encodes bytes as base64url without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def decode(value: str) -> bytes:
    """Decodes a base64url string to bytes."""
    padded = value + '=' * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(padded)
