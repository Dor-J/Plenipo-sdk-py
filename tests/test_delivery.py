"""Delivery helper tests."""

from plenipo.delivery import build_receipt


def test_build_receipt() -> None:
    assert build_receipt('01HX') == {'envelope_id': '01HX'}
