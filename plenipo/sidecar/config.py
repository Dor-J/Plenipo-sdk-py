"""Sidecar configuration and bind safety checks."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

LOCALHOST_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})

NO_AUTH_WARNING = (
    'WARNING: Plenipo sidecar running with --no-auth. '
    'Local API is unauthenticated. Use only on localhost for development.'
)


@dataclass(frozen=True)
class SidecarConfig:
    """Configuration for the local agent sidecar HTTP server."""

    host: str = '127.0.0.1'
    port: int = 8787
    capability: str = 'mcp'
    protocol: str = 'plenipo.message.v1'
    allow_remote_bind: bool = False
    event_buffer_size: int = 100
    token: str | None = None
    no_auth: bool = False
    print_token: bool = False
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SidecarSecurity:
    """Resolved sidecar security settings for middleware."""

    auth_enabled: bool
    token: str | None
    allowed_origins: frozenset[str]


def is_localhost_host(host: str) -> bool:
    """Returns True when the bind host is loopback-only."""
    return host.strip().lower() in LOCALHOST_HOSTS


def parse_allowed_origins(*values: str | None) -> tuple[str, ...]:
    """Parses comma-separated allowed browser origins."""
    origins: list[str] = []
    for value in values:
        if not value:
            continue
        for part in value.split(','):
            part = part.strip()
            if part:
                origins.append(part)
    return tuple(dict.fromkeys(origins))


def allowed_origins_from_config(config: SidecarConfig) -> frozenset[str]:
    """Returns allowed browser origins from config and environment."""
    env_origins = os.environ.get('PLENIPO_SIDECAR_ALLOWED_ORIGINS')
    merged = parse_allowed_origins(env_origins, *config.allowed_origins)
    return frozenset(merged)


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


def validate_no_auth_bind(host: str, *, no_auth: bool) -> None:
    """
    Validates that unauthenticated mode is not combined with non-localhost bind.

    Raises:
        ValueError: When --no-auth is used with a non-localhost bind address.
    """
    if no_auth and not is_localhost_host(host):
        raise ValueError(
            f'--no-auth cannot be used when binding to {host!r}. '
            'Authentication is required for non-localhost binds.'
        )


def remote_bind_warning(host: str) -> str:
    """Returns a loud warning message for non-localhost binds."""
    return (
        f'WARNING: Plenipo sidecar binding to {host} — '
        'local API may expose decrypted messages to the network. '
        'Use localhost unless you understand the risk.'
    )
