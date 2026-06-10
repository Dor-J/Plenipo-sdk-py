"""Sidecar configuration and bind safety checks."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plenipo.identity.store import plenipo_home

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
    signed_request_secret: str | None = None
    no_auth: bool = False
    print_token: bool = False
    allowed_origins: tuple[str, ...] = field(default_factory=tuple)
    tls_cert: str | None = None
    tls_key: str | None = None
    log_level: str = 'info'


@dataclass(frozen=True)
class SidecarSecurity:
    """Resolved sidecar security settings for middleware."""

    auth_enabled: bool
    token: str | None
    allowed_origins: frozenset[str]
    signed_request_secret: str | None = None


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


def sidecar_config_path(override: str | Path | None = None) -> Path:
    """Returns the sidecar config path from CLI, env, or the default home file."""
    if override is not None:
        return Path(override).expanduser()
    env_path = os.environ.get('PLENIPO_SIDECAR_CONFIG')
    if env_path:
        return Path(env_path).expanduser()
    return plenipo_home() / 'sidecar.toml'


def load_sidecar_config_file(
    path: str | Path | None = None,
    *,
    required: bool = False,
) -> dict[str, Any]:
    """Loads sidecar TOML config from top-level keys or a [sidecar] section."""
    target = sidecar_config_path(path)
    if not target.is_file():
        if required:
            raise FileNotFoundError(f'Sidecar config file not found: {target}')
        return {}

    with target.open('rb') as handle:
        raw = tomllib.load(handle)

    section = raw.get('sidecar')
    if isinstance(section, dict):
        return dict(section)
    return dict(raw)


def resolve_sidecar_config(
    *,
    config_path: str | Path | None = None,
    cli_values: dict[str, Any] | None = None,
) -> SidecarConfig:
    """
    Resolves sidecar settings with precedence: CLI > env > config file > defaults.
    """
    defaults = SidecarConfig()
    values: dict[str, Any] = {
        'host': defaults.host,
        'port': defaults.port,
        'capability': defaults.capability,
        'protocol': defaults.protocol,
        'allow_remote_bind': defaults.allow_remote_bind,
        'event_buffer_size': defaults.event_buffer_size,
        'token': defaults.token,
        'signed_request_secret': defaults.signed_request_secret,
        'no_auth': defaults.no_auth,
        'print_token': defaults.print_token,
        'allowed_origins': defaults.allowed_origins,
        'tls_cert': defaults.tls_cert,
        'tls_key': defaults.tls_key,
        'log_level': defaults.log_level,
    }
    values.update(_coerce_file_values(load_sidecar_config_file(config_path)))
    values.update(_env_values())
    if cli_values:
        values.update({key: value for key, value in cli_values.items() if value is not None})

    return SidecarConfig(
        host=str(values['host']),
        port=int(values['port']),
        capability=str(values['capability']),
        protocol=str(values['protocol']),
        allow_remote_bind=_bool_value(values['allow_remote_bind']),
        event_buffer_size=int(values['event_buffer_size']),
        token=_optional_str(values['token']),
        signed_request_secret=_optional_str(values['signed_request_secret']),
        no_auth=_bool_value(values['no_auth']),
        print_token=_bool_value(values['print_token']),
        allowed_origins=_origins_value(values['allowed_origins']),
        tls_cert=_optional_str(values['tls_cert']),
        tls_key=_optional_str(values['tls_key']),
        log_level=str(values['log_level']),
    )


def allowed_origins_from_config(config: SidecarConfig) -> frozenset[str]:
    """Returns allowed browser origins from the resolved config."""
    return frozenset(config.allowed_origins)


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


def validate_tls_config(config: SidecarConfig) -> None:
    """Validates local HTTPS configuration."""
    if bool(config.tls_cert) != bool(config.tls_key):
        raise ValueError('--tls-cert and --tls-key must be provided together')


def remote_bind_warning(host: str) -> str:
    """Returns a loud warning message for non-localhost binds."""
    return (
        f'WARNING: Plenipo sidecar binding to {host} — '
        'local API may expose decrypted messages to the network. '
        'Use localhost unless you understand the risk.'
    )


def _normalize_key(key: str) -> str:
    return key.replace('-', '_')


def _coerce_file_values(raw: dict[str, Any]) -> dict[str, Any]:
    supported = {
        'host',
        'port',
        'capability',
        'protocol',
        'allow_remote_bind',
        'event_buffer_size',
        'token',
        'signed_request_secret',
        'no_auth',
        'print_token',
        'allowed_origins',
        'tls_cert',
        'tls_key',
        'log_level',
    }
    return {
        normalized: value
        for key, value in raw.items()
        if (normalized := _normalize_key(str(key))) in supported
    }


def _env_values() -> dict[str, Any]:
    env_map = {
        'host': 'PLENIPO_SIDECAR_HOST',
        'port': 'PLENIPO_SIDECAR_PORT',
        'capability': 'PLENIPO_SIDECAR_CAPABILITY',
        'protocol': 'PLENIPO_SIDECAR_PROTOCOL',
        'allow_remote_bind': 'PLENIPO_SIDECAR_ALLOW_REMOTE_BIND',
        'event_buffer_size': 'PLENIPO_SIDECAR_EVENT_BUFFER_SIZE',
        'token': 'PLENIPO_SIDECAR_TOKEN',
        'signed_request_secret': 'PLENIPO_SIDECAR_SIGNING_SECRET',
        'no_auth': 'PLENIPO_SIDECAR_NO_AUTH',
        'print_token': 'PLENIPO_SIDECAR_PRINT_TOKEN',
        'allowed_origins': 'PLENIPO_SIDECAR_ALLOWED_ORIGINS',
        'tls_cert': 'PLENIPO_SIDECAR_TLS_CERT',
        'tls_key': 'PLENIPO_SIDECAR_TLS_KEY',
        'log_level': 'PLENIPO_SIDECAR_LOG_LEVEL',
    }
    return {key: value for key, env_key in env_map.items() if (value := os.environ.get(env_key))}


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _origins_value(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return parse_allowed_origins(value)
    if isinstance(value, (list, tuple)):
        return parse_allowed_origins(*(str(item) for item in value))
    return ()
