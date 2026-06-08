"""Runtime capability declaration for agent-first onboarding."""

from __future__ import annotations

import copy
from typing import Any

from plenipo.identity.provision import ensure_identity
from plenipo.identity.register_signing import document_fingerprint
from plenipo.identity.store import AgentIdentity, save_identity
from plenipo.identity.sync import sync_identity_with_core


def _update_document_capabilities(
    document: dict[str, Any],
    capabilities: list[str],
    *,
    replace: bool,
) -> dict[str, Any]:
    updated = copy.deepcopy(document)
    services = list(updated.get('service') or [])
    found = False

    for index, service in enumerate(services):
        if service.get('type') == 'PlenipoAgent':
            existing = list(service.get('capabilities') or [])
            merged = capabilities if replace else sorted(set(existing + capabilities))
            services[index] = {**service, 'capabilities': merged}
            found = True
            break

    if not found:
        services.append(
            {
                'id': f"{updated['id']}#plenipo",
                'type': 'PlenipoAgent',
                'serviceEndpoint': updated.get('serviceEndpoint'),
                'capabilities': capabilities,
            }
        )

    updated['service'] = services
    return updated


async def declare_capabilities(
    capabilities: list[str],
    *,
    replace: bool = False,
    identity: AgentIdentity | None = None,
) -> AgentIdentity:
    """Updates capabilities locally and syncs the DID document with Core."""
    current = identity or await ensure_identity()
    document = _update_document_capabilities(current.document, capabilities, replace=replace)

    pending = AgentIdentity(
        did=current.did,
        auth_secret_b64=current.auth_secret_b64,
        enc_secret_b64=current.enc_secret_b64,
        did_document_url=current.did_document_url,
        relay_url=current.relay_url,
        registry_url=current.registry_url,
        core_url=current.core_url,
        capabilities=_capabilities_from_document(document),
        created_at=current.created_at,
        document=document,
        did_document_mode=current.did_document_mode,
        core_registered=current.core_registered,
        registration_pending=True,
        last_registration_error=current.last_registration_error,
        document_fingerprint=document_fingerprint(document),
    )
    save_identity(pending)
    synced, _ = await sync_identity_with_core(pending)
    return synced


def _capabilities_from_document(document: dict[str, Any]) -> list[str]:
    for service in document.get('service') or []:
        if service.get('type') == 'PlenipoAgent':
            caps = service.get('capabilities')
            if isinstance(caps, list):
                return [str(cap) for cap in caps]
    return []
