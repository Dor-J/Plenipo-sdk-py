"""Agent identity storage and auto-provisioning."""

from plenipo.identity.capabilities import declare_capabilities
from plenipo.identity.provision import (
    create_local_identity,
    ensure_identity,
    provision_identity,
)
from plenipo.identity.store import AgentIdentity, identity_path, load_identity, save_identity
from plenipo.identity.sync import SyncIdentityResult, sync_identity_with_core, sync_result_to_dict
from plenipo.identity.urls import core_hosted_document_url

__all__ = [
    'AgentIdentity',
    'SyncIdentityResult',
    'core_hosted_document_url',
    'create_local_identity',
    'declare_capabilities',
    'ensure_identity',
    'identity_path',
    'load_identity',
    'provision_identity',
    'save_identity',
    'sync_identity_with_core',
    'sync_result_to_dict',
]
