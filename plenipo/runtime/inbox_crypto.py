"""Encrypted-at-rest inbox storage using a local sidecar store key."""

from __future__ import annotations

import os
import secrets
import stat
from base64 import urlsafe_b64decode, urlsafe_b64encode
from pathlib import Path

from nacl.secret import SecretBox

from plenipo.identity.store import plenipo_home

PLAINTEXT_ALG = 'nacl-secretbox-v1'
STORE_KEY_BYTES = 32


class SidecarStoreKeyError(RuntimeError):
    """Raised when the local sidecar store key is missing or invalid."""


def sidecar_store_key_path() -> Path:
    """Returns the path to the local sidecar store encryption key."""
    return plenipo_home() / 'sidecar-store.key'


def generate_sidecar_store_key() -> bytes:
    """Generates a 32-byte random store key."""
    return secrets.token_bytes(STORE_KEY_BYTES)


def write_sidecar_store_key(key: bytes, path: Path | None = None) -> Path:
    """Persists the store key with restrictive permissions where supported."""
    if len(key) != STORE_KEY_BYTES:
        raise ValueError('sidecar store key must be 32 bytes')
    target = path or sidecar_store_key_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(key)
    try:
        if os.name != 'nt':
            os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return target


def read_sidecar_store_key(path: Path | None = None) -> bytes | None:
    """Reads the store key from disk when present."""
    target = path or sidecar_store_key_path()
    if not target.is_file():
        return None
    key = target.read_bytes()
    if len(key) != STORE_KEY_BYTES:
        raise SidecarStoreKeyError(f'invalid sidecar store key at {target}')
    return key


def resolve_sidecar_store_key(
    *,
    generate_if_missing: bool = True,
    path: Path | None = None,
) -> bytes:
    """Resolves the local sidecar store key, generating it on first use when allowed."""
    existing = read_sidecar_store_key(path)
    if existing is not None:
        return existing
    if not generate_if_missing:
        raise SidecarStoreKeyError(
            'sidecar store key missing; cannot decrypt encrypted local inbox',
        )
    key = generate_sidecar_store_key()
    write_sidecar_store_key(key, path)
    return key


def encrypt_plaintext(plaintext: str, key: bytes) -> tuple[str, str]:
    """Encrypts plaintext for inbox storage. Returns (ciphertext_b64, nonce_b64)."""
    if len(key) != STORE_KEY_BYTES:
        raise ValueError('sidecar store key must be 32 bytes')
    box = SecretBox(key)
    encrypted = box.encrypt(plaintext.encode('utf-8'))
    return (
        urlsafe_b64encode(encrypted.ciphertext).decode('ascii').rstrip('='),
        urlsafe_b64encode(encrypted.nonce).decode('ascii').rstrip('='),
    )


def decrypt_plaintext(ciphertext_b64: str, nonce_b64: str, key: bytes) -> str:
    """Decrypts inbox plaintext ciphertext."""
    if len(key) != STORE_KEY_BYTES:
        raise ValueError('sidecar store key must be 32 bytes')

    def _pad(value: str) -> str:
        return value + '=' * (-len(value) % 4)

    ciphertext = urlsafe_b64decode(_pad(ciphertext_b64))
    nonce = urlsafe_b64decode(_pad(nonce_b64))
    box = SecretBox(key)
    try:
        plain = box.decrypt(ciphertext, nonce)
    except Exception as exc:
        raise SidecarStoreKeyError('failed to decrypt local inbox plaintext') from exc
    return plain.decode('utf-8')
