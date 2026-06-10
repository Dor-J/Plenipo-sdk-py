"""Agent identity storage and auto-provisioning."""

from plenipo.identity.capabilities import declare_capabilities
from plenipo.identity.provision import (
    create_local_identity,
    ensure_identity,
    provision_identity,
)
from plenipo.identity.store import AgentIdentity, identity_path, load_identity, save_identity
from plenipo.identity.sync import SyncIdentityResult, sync_identity_with_core, sync_result_to_dict
from plenipo.identity.register_signing import sign_rotation_payload
from plenipo.identity.urls import (
    core_hosted_document_url,
    external_did_web_document_url,
    is_core_hosted_local_did,
    validate_production_did_web,
)

__all__ = [
    'AgentIdentity',
    'SyncIdentityResult',
    'core_hosted_document_url',
    'create_local_identity',
    'declare_capabilities',
    'ensure_identity',
    'external_did_web_document_url',
    'identity_path',
    'is_core_hosted_local_did',
    'load_identity',
    'provision_identity',
    'save_identity',
    'sign_rotation_payload',
    'sync_identity_with_core',
    'sync_result_to_dict',
    'validate_production_did_web',
]
