"""Public package import surface tests."""

from __future__ import annotations

import plenipo


def test_root_import_surface_is_explicit() -> None:
    expected = {
        'PlenipoAgentRuntime',
        'PlenipoClient',
        'PlenipoMCP',
        'PlenipoSidecarClient',
        'SidecarClientError',
        'build_receipt',
        'discover_agents',
        'ensure_identity',
        'get_delivery_status',
        'sync_identity_with_core',
    }

    assert expected.issubset(set(plenipo.__all__))
    assert plenipo.__version__ == '0.0.1'
    assert plenipo.PlenipoClient is not None
    assert plenipo.PlenipoSidecarClient is not None
