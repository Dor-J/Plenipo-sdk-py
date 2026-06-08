"""Persistent agent identity at ~/.plenipo/identity.json."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

DidDocumentMode = Literal['core_hosted', 'external']


@dataclass(frozen=True)
class AgentIdentity:
    """Locally persisted Plenipo agent identity."""

    did: str
    auth_secret_b64: str
    enc_secret_b64: str
    did_document_url: str
    relay_url: str
    registry_url: str
    core_url: str
    capabilities: list[str]
    created_at: str
    document: dict[str, Any]
    did_document_mode: DidDocumentMode = 'core_hosted'
    core_registered: bool = False
    registration_pending: bool = True
    last_registration_error: str | None = None
    document_fingerprint: str | None = None


def plenipo_home() -> Path:
    """Returns the Plenipo home directory."""
    override = os.environ.get('PLENIPO_HOME')
    if override:
        return Path(override).expanduser()
    return Path.home() / '.plenipo'


def identity_path() -> Path:
    """Returns the default identity file path."""
    return plenipo_home() / 'identity.json'


def load_identity(path: Path | None = None) -> AgentIdentity | None:
    """Loads identity from disk when present."""
    target = path or identity_path()
    if not target.is_file():
        return None

    raw = json.loads(target.read_text(encoding='utf-8'))
    return AgentIdentity(
        did=str(raw['did']),
        auth_secret_b64=str(raw['auth_secret_b64']),
        enc_secret_b64=str(raw['enc_secret_b64']),
        did_document_url=str(raw['did_document_url']),
        relay_url=str(raw['relay_url']),
        registry_url=str(raw['registry_url']),
        core_url=str(raw['core_url']),
        capabilities=list(raw.get('capabilities', [])),
        created_at=str(raw.get('created_at', '')),
        document=dict(raw['document']),
        did_document_mode=str(raw.get('did_document_mode', 'core_hosted')),
        core_registered=bool(raw.get('core_registered', True)),
        registration_pending=bool(raw.get('registration_pending', False)),
        last_registration_error=raw.get('last_registration_error'),
        document_fingerprint=raw.get('document_fingerprint'),
    )


def save_identity(identity: AgentIdentity, path: Path | None = None) -> Path:
    """Persists identity to disk with restrictive permissions."""
    target = path or identity_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(identity)
    target.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def identity_from_create_result(
    *,
    did: str,
    auth_secret_b64: str,
    enc_secret_b64: str,
    did_document_url: str,
    document: dict[str, Any],
    relay_url: str,
    registry_url: str,
    core_url: str,
    capabilities: list[str] | None = None,
    did_document_mode: DidDocumentMode = 'core_hosted',
    core_registered: bool = False,
    registration_pending: bool = True,
    last_registration_error: str | None = None,
    document_fingerprint: str | None = None,
) -> AgentIdentity:
    """Builds an AgentIdentity from DID creation output."""
    caps = capabilities or _capabilities_from_document(document)
    return AgentIdentity(
        did=did,
        auth_secret_b64=auth_secret_b64,
        enc_secret_b64=enc_secret_b64,
        did_document_url=did_document_url,
        relay_url=relay_url,
        registry_url=registry_url,
        core_url=core_url,
        capabilities=caps,
        created_at=datetime.now(timezone.utc).isoformat(),
        document=document,
        did_document_mode=did_document_mode,
        core_registered=core_registered,
        registration_pending=registration_pending,
        last_registration_error=last_registration_error,
        document_fingerprint=document_fingerprint,
    )


def _capabilities_from_document(document: dict[str, Any]) -> list[str]:
    services = document.get('service') or []
    for service in services:
        if service.get('type') == 'PlenipoAgent':
            caps = service.get('capabilities')
            if isinstance(caps, list):
                return [str(cap) for cap in caps]
    return []
