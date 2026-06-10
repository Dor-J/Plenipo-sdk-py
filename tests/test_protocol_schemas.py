"""Validates public protocol fixtures against shared JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / 'schemas' / 'protocol'
FIXTURE = ROOT / 'test-fixtures' / 'protocol' / 'canonical.json'

SCHEMA_FIXTURE_MAP = {
    'envelope.schema.json': 'envelope',
    'route-record.schema.json': 'routeRecord',
    'send-ack.schema.json': 'sendAck',
    'delivery-receipt.schema.json': 'deliveryReceipt',
    'receipt-list-result.schema.json': 'receiptListResult',
    'sidecar-events-response.schema.json': 'sidecarEventsResponse',
    'sidecar-status.schema.json': 'sidecarStatus',
    'sidecar-send-request.schema.json': 'sidecarSendRequest',
    'sidecar-send-response.schema.json': 'sidecarSendResponse',
    'error-response.schema.json': 'errorResponse',
}


def _schemas() -> dict[str, dict[str, object]]:
    schemas: dict[str, dict[str, object]] = {}
    for path in SCHEMA_DIR.glob('*.schema.json'):
        schema = json.loads(path.read_text(encoding='utf-8'))
        schemas[path.name] = schema
        schemas[str(schema['$id'])] = schema
    return schemas


def test_canonical_protocol_fixtures_validate_against_json_schemas() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    schemas = _schemas()

    for schema_name, fixture_key in SCHEMA_FIXTURE_MAP.items():
        schema = schemas[schema_name]
        resolver = RefResolver.from_schema(schema, store=schemas)
        validator = Draft202012Validator(schema, resolver=resolver)
        errors = sorted(validator.iter_errors(fixture[fixture_key]), key=lambda err: err.path)
        assert errors == []


def test_error_schema_codes_match_public_error_catalog() -> None:
    schema = _schemas()['error-response.schema.json']
    code_enum = set(schema['properties']['code']['enum'])  # type: ignore[index]
    catalog = (ROOT / 'ERRORS.md').read_text(encoding='utf-8')
    for code in code_enum:
        assert f'`{code}`' in catalog
