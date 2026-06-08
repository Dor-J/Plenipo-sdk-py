"""Auto-provision local agent identities."""

from __future__ import annotations

import os
import secrets
from typing import Any

from plenipo.did import create_did_document
from plenipo.identity.store import (
    AgentIdentity,
    identity_from_create_result,
    load_identity,
    save_identity,
)
from plenipo.identity.sync import sync_identity_with_core
from plenipo.identity.urls import core_hosted_document_url
from plenipo.mcp.runtime import McpRuntimeConfig


def _default_core_url() -> str:
    return os.environ.get('PLENIPO_CORE_URL', 'http://localhost:4000')


def _default_relay_url() -> str:
    return os.environ.get('PLENIPO_RELAY_URL', 'ws://localhost:4000/agent/websocket')


def _default_registry_url() -> str:
    return os.environ.get('PLENIPO_REGISTRY_URL', 'http://localhost:4001')


def _env_identity_complete() -> AgentIdentity | None:
    """Returns identity from env when all required fields are present."""
    did = os.environ.get('PLENIPO_DID')
    auth = os.environ.get('PLENIPO_AUTH_SECRET_B64') or os.environ.get('PLENIPO_DID_PRIVATE_KEY')
    doc_url = os.environ.get('PLENIPO_DID_DOCUMENT_URL')
    if not did or not auth or not doc_url:
        return None

    relay = _default_relay_url()
    registry = _default_registry_url()
    core = _default_core_url()
    enc = os.environ.get('PLENIPO_ENC_SECRET_B64', '')
    document: dict[str, Any] = {
        'id': did,
        'service': [
            {
                'type': 'PlenipoAgent',
                'serviceEndpoint': relay,
                'capabilities': ['general'],
            }
        ],
    }

    return identity_from_create_result(
        did=did,
        auth_secret_b64=auth,
        enc_secret_b64=enc,
        did_document_url=doc_url,
        document=document,
        relay_url=relay,
        registry_url=registry,
        core_url=core,
        did_document_mode='external',
        core_registered=True,
        registration_pending=False,
    )


def create_local_identity(
    *,
    core_url: str | None = None,
    relay_url: str | None = None,
    registry_url: str | None = None,
) -> AgentIdentity:
    """Generates keys and persists identity locally without contacting Core."""
    core = core_url or _default_core_url()
    relay = relay_url or _default_relay_url()
    registry = registry_url or _default_registry_url()
    agent_id = secrets.token_hex(8)

    created = create_did_document(
        'localhost',
        relay,
        path_segments=['agents', agent_id],
    )

    identity = identity_from_create_result(
        did=created.did,
        auth_secret_b64=created.auth_secret_b64,
        enc_secret_b64=created.enc_secret_b64,
        did_document_url=core_hosted_document_url(core, created.did),
        document=created.document,
        relay_url=relay,
        registry_url=registry,
        core_url=core,
        did_document_mode='core_hosted',
        core_registered=False,
        registration_pending=True,
    )
    save_identity(identity)
    return identity


async def provision_identity(
    *,
    core_url: str | None = None,
    relay_url: str | None = None,
    registry_url: str | None = None,
) -> AgentIdentity:
    """Creates a local identity and attempts immediate Core registration."""
    identity = create_local_identity(
        core_url=core_url,
        relay_url=relay_url,
        registry_url=registry_url,
    )
    synced, _ = await sync_identity_with_core(identity)
    return synced


async def ensure_identity() -> AgentIdentity:
    """Loads env, file, or creates local identity; best-effort Core sync."""
    env_identity = _env_identity_complete()
    if env_identity is not None:
        return env_identity

    stored = load_identity()
    if stored is None:
        stored = create_local_identity()

    if stored.did_document_mode == 'core_hosted' and (
        stored.registration_pending or not stored.core_registered
    ):
        synced, _ = await sync_identity_with_core(stored)
        return synced

    return stored


def identity_to_mcp_config(identity: AgentIdentity) -> McpRuntimeConfig:
    """Maps a persisted identity to MCP runtime configuration."""
    return McpRuntimeConfig(
        did=identity.did,
        auth_secret_b64=identity.auth_secret_b64,
        did_document_url=identity.did_document_url,
        relay_url=identity.relay_url,
        enc_secret_b64=identity.enc_secret_b64 or None,
        registry_url=identity.registry_url,
    )
