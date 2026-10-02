"""The passphrase-protected master key backup (``.cfk``).

Spec secret "Release plaintext only to a present human in the desktop app" and
vault-sync "Import a master key after showing whose key it is".
"""

from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet

from coffer.domain.sync.errors import (
    MasterKeyFileInvalid,
    MasterKeyPassphraseTooShort,
    MasterKeyPassphraseWrong,
)
from coffer.infrastructure.secret import key_backup

_PASS = "correct horse"


@pytest.fixture(autouse=True)
def _cheap_scrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shipped cost is ~128 MiB per derivation; the format is what is tested."""
    monkeypatch.setattr(key_backup, "_N", 2**10)


@pytest.fixture
def key() -> bytes:
    return Fernet.generate_key()


def test_a_backup_opens_with_its_passphrase_and_never_holds_the_key_in_the_clear(
    key: bytes,
) -> None:
    text = key_backup.wrap(key, _PASS)

    assert key.decode() not in text and _PASS not in text
    assert key_backup.unwrap(text, _PASS) == key


def test_peek_names_the_fingerprint_without_the_passphrase(key: bytes) -> None:
    protected = key_backup.peek(key_backup.wrap(key, _PASS))
    bare = key_backup.peek(key.decode() + "\n")

    assert protected == key_backup.KeyFileInfo(key_backup.key_fingerprint(key), True)
    assert bare == key_backup.KeyFileInfo(key_backup.key_fingerprint(key), False)
    assert len(protected.fingerprint) == 12


def test_a_wrong_or_missing_passphrase_is_refused(key: bytes) -> None:
    text = key_backup.wrap(key, _PASS)

    with pytest.raises(MasterKeyPassphraseWrong):
        key_backup.unwrap(text, "not the passphrase")
    with pytest.raises(MasterKeyPassphraseWrong):
        key_backup.unwrap(text, None)


def test_a_short_passphrase_writes_no_backup(key: bytes) -> None:
    with pytest.raises(MasterKeyPassphraseTooShort):
        key_backup.wrap(key, "short")


def test_a_bare_key_needs_no_passphrase(key: bytes) -> None:
    assert key_backup.unwrap(key.decode(), None) == key


@pytest.mark.parametrize(
    "material",
    ["", "   ", "not-a-key", "{not json", json.dumps({"coffer_master_key_backup": 99})],
)
def test_material_that_is_no_key_file_is_invalid(material: str) -> None:
    with pytest.raises(MasterKeyFileInvalid):
        key_backup.unwrap(material, _PASS)


def test_parameters_that_would_exhaust_memory_are_refused(key: bytes) -> None:
    doc = json.loads(key_backup.wrap(key, _PASS))
    doc["kdf"]["n"] = 2**30

    with pytest.raises(MasterKeyFileInvalid):
        key_backup.unwrap(json.dumps(doc), _PASS)


def test_parameters_that_each_pass_their_bound_but_need_gigabytes_are_refused(key: bytes) -> None:
    """scrypt needs 128 * r * N bytes: N=2^20 with r=16 is 2 GiB."""
    doc = json.loads(key_backup.wrap(key, _PASS))
    doc["kdf"]["n"], doc["kdf"]["r"] = 2**20, 16

    with pytest.raises(MasterKeyFileInvalid):
        key_backup.unwrap(json.dumps(doc), _PASS)


def test_a_header_fingerprint_that_is_not_the_keys_is_refused(key: bytes) -> None:
    doc = json.loads(key_backup.wrap(key, _PASS))
    doc["fingerprint"] = "0" * 12

    with pytest.raises(MasterKeyFileInvalid):
        key_backup.unwrap(json.dumps(doc), _PASS)
