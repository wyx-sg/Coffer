"""fernet_created_at — read the encryption epoch out of a Fernet token."""

from __future__ import annotations

import base64

from coffer.domain.sync.fernet_time import fernet_created_at
from cryptography.fernet import Fernet


def test_extracts_embedded_encryption_time() -> None:
    key = Fernet.generate_key()
    blob = Fernet(key).encrypt_at_time(b"secret", 1_750_000_000)
    assert fernet_created_at(blob) == 1_750_000_000


def test_no_key_needed_and_whitespace_tolerated() -> None:
    key = Fernet.generate_key()
    blob = Fernet(key).encrypt_at_time(b"secret", 42)
    assert fernet_created_at(b"\n" + blob + b"\n") == 42


def test_none_for_garbage() -> None:
    assert fernet_created_at(b"not-a-token") is None
    assert fernet_created_at(b"") is None


def test_none_for_wrong_version_byte() -> None:
    raw = b"\x00" + (1_750_000_000).to_bytes(8, "big") + b"\x00" * 20
    assert fernet_created_at(base64.urlsafe_b64encode(raw)) is None


def test_none_for_truncated_token() -> None:
    raw = b"\x80\x00\x00"
    assert fernet_created_at(base64.urlsafe_b64encode(raw)) is None
