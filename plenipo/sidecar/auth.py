"""Sidecar bearer token generation, storage, and resolution."""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from plenipo.identity.store import plenipo_home


def sidecar_token_path() -> Path:
    """Returns the default sidecar bearer token file path."""
    return plenipo_home() / 'sidecar-token'


def generate_sidecar_token() -> str:
    """Generates a cryptographically secure bearer token."""
    return secrets.token_urlsafe(32)


def read_sidecar_token_file(path: Path | None = None) -> str | None:
    """Reads a bearer token from disk when present."""
    target = path or sidecar_token_path()
    if not target.is_file():
        return None
    token = target.read_text(encoding='utf-8').strip()
    return token or None


def write_sidecar_token_file(token: str, path: Path | None = None) -> Path:
    """Persists a bearer token with restrictive permissions where supported."""
    target = path or sidecar_token_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(token.strip() + '\n', encoding='utf-8')
    try:
        if os.name != 'nt':
            os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return target


def resolve_sidecar_token(
    *,
    cli_token: str | None = None,
    env_token: str | None = None,
    no_auth: bool = False,
    generate_if_missing: bool = True,
) -> tuple[str | None, Path | None, bool]:
    """
    Resolves the sidecar bearer token.

    Priority: CLI token > env token > token file > generated token.

    Returns:
        Tuple of (token or None when no_auth, token file path, generated_new).
    """
    token_path = sidecar_token_path()

    if no_auth:
        return None, token_path, False

    if cli_token:
        return cli_token.strip(), token_path, False

    env = env_token or os.environ.get('PLENIPO_SIDECAR_TOKEN')
    if env:
        return env.strip(), token_path, False

    existing = read_sidecar_token_file(token_path)
    if existing:
        return existing, token_path, False

    if generate_if_missing:
        token = generate_sidecar_token()
        write_sidecar_token_file(token, token_path)
        return token, token_path, True

    return None, token_path, False


def constant_time_token_match(provided: str, expected: str) -> bool:
    """Compares bearer tokens in constant time."""
    return secrets.compare_digest(provided.strip(), expected.strip())
