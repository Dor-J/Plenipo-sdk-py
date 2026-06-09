"""Cross-SDK protocol fixture compatibility tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

from plenipo.client.relay import _generate_ulid
from plenipo.did.create import create_did_document
from plenipo.route_defaults import default_route_service_fields
from plenipo.sidecar.models import events_response

FIXTURES = Path(__file__).resolve().parents[2] / 'test-fixtures' / 'protocol' / 'canonical.json'


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURES.read_text(encoding='utf-8'))


def test_route_record_matches_fixture() -> None:
    data = _fixture()
    expected = data['routeRecord']
    assert isinstance(expected, dict)
    defaults = default_route_service_fields()
    assert defaults['protocols'] == expected['protocols']
    assert defaults['payment'] == expected['payment']
    assert defaults['limits'] == expected['limits']
    assert defaults['encryption'] == expected['encryption']


def test_multibase_keys_are_single_z_prefix() -> None:
    created = create_did_document(
        'localhost',
        relay_url='ws://127.0.0.1:4000/agent/websocket',
        path_segments=['agents', 'fixture'],
    )
    for method in created.document['verificationMethod']:
        multibase = str(method['publicKeyMultibase'])
        assert multibase.startswith('z')
        assert not multibase.startswith('zz')


def test_ulid_uses_crockford_alphabet_only() -> None:
    data = _fixture()
    alphabet = set(str(data['ulidAlphabet']))
    invalid = set(data['invalidUlidChars'])
    assert isinstance(invalid, set)
    pattern = re.compile(r'^[0-9A-HJKMNP-TV-Z]{26}$')
    for _ in range(20):
        ulid = _generate_ulid()
        assert pattern.match(ulid)
        assert set(ulid).issubset(alphabet)
        assert not set(ulid) & invalid


def test_events_response_shape_matches_fixture() -> None:
    data = _fixture()
    expected = data['sidecarEventsResponse']
    assert isinstance(expected, dict)
    response = events_response(
        [
            {
                'id': 1,
                'type': 'message',
                'envelope_id': '01JEXAMPLEULIDEXAMPLE12',
                'has_plaintext': True,
            }
        ],
        next_after_id=2,
    )
    assert response['next_after_id'] == expected['next_after_id']
    assert response['since_id'] == expected['since_id']
    assert isinstance(response['events'], list)
