"""Core registration sync for local agent identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from plenipo.identity.register import register_document
from plenipo.identity.register_signing import document_fingerprint
from plenipo.identity.store import AgentIdentity, save_identity
from plenipo.identity.sync_errors import sync_warnings_from_error


@dataclass(frozen=True)
class SyncIdentityResult:
    """Result of syncing a local identity with Core."""

    ok: bool
    did: str
    core_registered: bool
    registration_pending: bool
    document_fingerprint: str | None
    warnings: list[str]


async def sync_identity_with_core(identity: AgentIdentity) -> tuple[AgentIdentity, SyncIdentityResult]:
    """Registers or updates the identity DID document with Core."""
    warnings: list[str] = []
    fingerprint = document_fingerprint(identity.document)

    try:
        response = await register_document(
            identity.core_url,
            identity.document,
            identity.auth_secret_b64,
        )
        updated = AgentIdentity(
            did=identity.did,
            auth_secret_b64=identity.auth_secret_b64,
            enc_secret_b64=identity.enc_secret_b64,
            did_document_url=identity.did_document_url,
            relay_url=identity.relay_url,
            registry_url=identity.registry_url,
            core_url=identity.core_url,
            capabilities=identity.capabilities,
            created_at=identity.created_at,
            document=identity.document,
            did_document_mode=identity.did_document_mode,
            core_registered=True,
            registration_pending=False,
            last_registration_error=None,
            document_fingerprint=str(response.get('document_fingerprint', fingerprint)),
        )
        save_identity(updated)
        return updated, SyncIdentityResult(
            ok=True,
            did=updated.did,
            core_registered=True,
            registration_pending=False,
            document_fingerprint=updated.document_fingerprint,
            warnings=warnings,
        )
    except (httpx.HTTPError, httpx.TimeoutException, ValueError, ConnectionError, OSError) as exc:
        pending = AgentIdentity(
            did=identity.did,
            auth_secret_b64=identity.auth_secret_b64,
            enc_secret_b64=identity.enc_secret_b64,
            did_document_url=identity.did_document_url,
            relay_url=identity.relay_url,
            registry_url=identity.registry_url,
            core_url=identity.core_url,
            capabilities=identity.capabilities,
            created_at=identity.created_at,
            document=identity.document,
            did_document_mode=identity.did_document_mode,
            core_registered=False,
            registration_pending=True,
            last_registration_error=str(exc),
            document_fingerprint=fingerprint,
        )
        save_identity(pending)
        warnings.extend(sync_warnings_from_error(exc))
        return pending, SyncIdentityResult(
            ok=False,
            did=pending.did,
            core_registered=False,
            registration_pending=True,
            document_fingerprint=fingerprint,
            warnings=warnings,
        )


def sync_result_to_dict(result: SyncIdentityResult) -> dict[str, Any]:
    """Serializes a sync result for MCP tool responses."""
    return {
        'ok': result.ok,
        'did': result.did,
        'core_registered': result.core_registered,
        'registration_pending': result.registration_pending,
        'document_fingerprint': result.document_fingerprint,
        'warnings': result.warnings,
    }
