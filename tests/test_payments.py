"""Tests for x402 payment helpers."""

from plenipo.payments import (
    build_bundle_payment,
    build_relay_payment,
    encode_payment_payload,
    parse_payment_required,
)
import base64
import json


def test_encode_payment_payload_roundtrip() -> None:
    payload = {
        'payment_id': 'pay_1',
        'agent_did': 'did:web:a.local',
        'purpose': 'bundle_purchase',
        'bundle_id': 'starter',
        'amount_cents': 100,
    }
    encoded = encode_payment_payload(payload)
    decoded = json.loads(base64.urlsafe_b64decode(encoded + '=='))
    assert decoded['bundle_id'] == 'starter'


def test_parse_payment_required() -> None:
    raw = json.dumps({'accepts': [], 'scheme': 'x402-dev'}).encode('utf-8')
    header = base64.urlsafe_b64encode(raw).decode('utf-8').rstrip('=')
    parsed = parse_payment_required(header)
    assert parsed['scheme'] == 'x402-dev'


def test_build_relay_payment() -> None:
    proof = build_relay_payment('did:web:a.local', 1, '01JENV')
    decoded = json.loads(base64.urlsafe_b64decode(proof + '=='))
    assert decoded['purpose'] == 'relay'
    assert decoded['envelope_id'] == '01JENV'


def test_build_bundle_payment() -> None:
    proof = build_bundle_payment('did:web:a.local', 'starter', 100)
    decoded = json.loads(base64.urlsafe_b64decode(proof + '=='))
    assert decoded['bundle_id'] == 'starter'
