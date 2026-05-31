"""Tests for base64url helpers."""

from plenipo.crypto import base64url


def test_round_trip() -> None:
    data = b'\x01\x02\xff'
    assert base64url.decode(base64url.encode(data)) == data
