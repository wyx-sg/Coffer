"""Ordering two credential ciphertexts without the key.

Covers `openspec/specs/vault-sync/spec.md` "Credentials" (the fresher ciphertext wins),
for the pure domain in `coffer.domain.sync.fernet_time`.
"""

from __future__ import annotations

import base64
import struct

import pytest
from cryptography.fernet import Fernet

from coffer.domain.sync.fernet_time import encrypted_at, is_fresher

_KEY = Fernet.generate_key()


def _token(at: int, secret: bytes = b"ghp_example") -> bytes:
    """A genuine Fernet token, stamped at a chosen second."""
    return Fernet(_KEY).encrypt_at_time(secret, at)


def _handmade(version: int, timestamp: int, payload: bytes = b"\x00" * 64) -> bytes:
    return base64.urlsafe_b64encode(bytes([version]) + struct.pack(">Q", timestamp) + payload)


def test_a_real_token_reports_the_second_it_was_encrypted_at() -> None:
    assert encrypted_at(_token(1_700_000_000)) == 1_700_000_000


def test_the_timestamp_is_readable_without_the_key_that_made_it() -> None:
    # The whole point of the module: a machine holding a different master key
    # can still order the blob.
    foreign = Fernet(Fernet.generate_key()).encrypt_at_time(b"secret", 1_650_000_123)
    assert encrypted_at(foreign) == 1_650_000_123


def test_two_tokens_of_the_same_secret_are_distinguished_by_their_stamps() -> None:
    assert encrypted_at(_token(10, b"same")) == 10
    assert encrypted_at(_token(99, b"same")) == 99


def test_a_blob_that_is_not_base64_is_unreadable() -> None:
    assert encrypted_at(b"this is not a fernet token, it is prose") is None


def test_a_blob_too_short_to_hold_a_header_is_unreadable() -> None:
    assert encrypted_at(base64.urlsafe_b64encode(b"\x80" + b"\x00" * 3)) is None


def test_an_empty_blob_is_unreadable() -> None:
    assert encrypted_at(b"") is None


def test_a_blob_with_a_foreign_version_byte_is_unreadable() -> None:
    # Well-formed base64, right length, wrong format — Fernet defines 0x80 and
    # nothing else, so the eight bytes after it are not a timestamp.
    assert encrypted_at(_handmade(0x7F, 1_700_000_000)) is None


def test_a_far_future_stamp_is_read_as_an_unsigned_big_endian_quad() -> None:
    stamp = 2**33 + 7  # past what 32 bits could carry
    assert encrypted_at(_handmade(0x80, stamp)) == stamp


def test_the_later_ciphertext_is_the_fresher_one() -> None:
    assert is_fresher(_token(200), _token(100)) is True


def test_an_earlier_ciphertext_does_not_displace_the_incumbent() -> None:
    assert is_fresher(_token(100), _token(200)) is False


def test_a_tie_keeps_the_incumbent() -> None:
    # Two machines re-encrypting in the same second must not flip-flop.
    assert is_fresher(_token(500, b"a"), _token(500, b"b")) is False


@pytest.mark.parametrize("unreadable", [b"", b"not-a-token!!", _handmade(0x7F, 1)])
def test_an_unreadable_candidate_never_wins(unreadable: bytes) -> None:
    assert is_fresher(unreadable, _token(1_700_000_000)) is False


@pytest.mark.parametrize("unreadable", [b"", b"not-a-token!!", _handmade(0x7F, 1)])
def test_an_unreadable_incumbent_is_not_replaced(unreadable: bytes) -> None:
    # "Unknown" on either side means this comparator must not decide.
    assert is_fresher(_token(1_700_000_000), unreadable) is False
