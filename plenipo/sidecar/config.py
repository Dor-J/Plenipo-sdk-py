"""Sidecar configuration and bind safety checks."""

from __future__ import annotations

from dataclasses import dataclass

LOCALHOST_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})


@dataclass(frozen=True)
class SidecarConfig:
    """Configuration for the local agent sidecar HTTP server."""

    host: str = '127.0.0.1'
    port: int = 8787
    capability: str = 'mcp'
    protocol: str = 'plenipo.message.v1'
    allow_remote_bind: bool = False
    event_buffer_size: int = 100


def is_localhost_host(host: str) -> bool:
    """Returns True when the bind host is loopback-only."""
    return host.strip().lower() in LOCALHOST_HOSTS


def validate_bind_host(host: str, *, allow_remote_bind: bool) -> None:
    """
    Validates bind host safety.

    Raises:
        ValueError: When binding to a non-localhost host without explicit opt-in.
    """
    if not is_localhost_host(host) and not allow_remote_bind:
        raise ValueError(
            f'Binding to {host!r} requires --allow-remote-bind for safety. '
            'Default is localhost-only.'
        )


def remote_bind_warning(host: str) -> str:
    """Returns a loud warning message for non-localhost binds."""
    return (
        f'WARNING: Plenipo sidecar binding to {host} — '
        'local API may expose decrypted messages to the network. '
        'Use localhost unless you understand the risk.'
    )
