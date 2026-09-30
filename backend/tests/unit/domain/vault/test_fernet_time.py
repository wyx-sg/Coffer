"""A credential file's encryption time, read without the key (the credential
store's ``updated_at``; the order sync settles two copies of a ref by)."""

from __future__ import annotations

import base64
import struct

from cryptography.fernet import Fernet

from coffer.domain.vault.fernet_time import encrypted_at, is_fresher

_KEY = Fernet.generate_key()


def _token(at: int) -> bytes:
    return Fernet(_KEY).encrypt_at_time(b"ghp_example", at)


def test_a_token_reports_its_second_even_with_the_files_trailing_newline() -> None:
    assert encrypted_at(_token(1_700_000_000)) == 1_700_000_000
    assert encrypted_at(_token(1_700_000_000) + b"\n") == 1_700_000_000


def test_a_foreign_keys_token_is_still_readable() -> None:
    foreign = Fernet(Fernet.generate_key()).encrypt_at_time(b"s", 1_650_000_123)
    assert encrypted_at(foreign) == 1_650_000_123


def test_what_is_not_a_token_is_unknown() -> None:
    assert encrypted_at(b"prose, not a token") is None
    assert encrypted_at(base64.urlsafe_b64encode(b"\x80\x00")) is None
    assert (
        encrypted_at(base64.urlsafe_b64encode(b"\x81" + struct.pack(">Q", 5) + b"x" * 40)) is None
    )


def test_only_a_strictly_later_encryption_is_fresher() -> None:
    assert is_fresher(_token(20), _token(10))
    assert not is_fresher(_token(10), _token(20))
    assert not is_fresher(_token(10), _token(10))
    assert not is_fresher(b"junk", _token(10))
