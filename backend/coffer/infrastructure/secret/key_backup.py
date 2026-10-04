"""The master key backup file: ``coffer-master-key.cfk``, passphrase-protected.

Spec secret "Release plaintext only to a present human in the desktop app"
and vault-sync "Import a master key after showing whose key it is".

The backup is the one way the master key leaves a machine (principle I), so
the file does not hold the key in the clear: it holds the key encrypted under
a key derived from a passphrase the person typed. A copy that lands in a
Downloads folder, a synced drive or a mail attachment opens nothing without
the passphrase.

Format — one JSON object::

    {
      "coffer_master_key_backup": 1,
      "fingerprint": "7f3a91c25d0e",
      "kdf": {"name": "scrypt", "salt": "<base64>", "n": 131072, "r": 8, "p": 1},
      "key": "<Fernet token of the master key>"
    }

The wrapping key is ``scrypt(passphrase, salt)``, 32 bytes, used as a Fernet
key, so a wrong passphrase fails the token's HMAC instead of yielding a wrong
key. The fingerprint is in the clear on purpose: it is the same short hash
every machine already publishes in its sync descriptor, and it is what lets
an import show "Key in the file … · different" before the passphrase is typed.
It is checked against the unwrapped key, so an edited header is refused rather
than believed.

A bare Fernet key (a development build's ``master.key``) is still accepted on
import; it needs no passphrase, and costs one branch here.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from coffer.domain.sync.errors import (
    MasterKeyFileInvalid,
    MasterKeyPassphraseTooShort,
    MasterKeyPassphraseWrong,
)

#: The name the export writes; a number is added before the suffix when a file
#: of that name already exists, so an export never overwrites.
BACKUP_FILE_NAME = "coffer-master-key.cfk"
#: The shortest passphrase an export accepts.
MIN_PASSPHRASE_LENGTH = 8

_FORMAT_KEY = "coffer_master_key_backup"
_FORMAT_VERSION = 1
# scrypt at N=2^17, r=8: ~128 MiB and a few hundred milliseconds per attempt.
_N, _R, _P = 2**17, 8, 1
# Upper bounds for a file's own parameters, so a crafted file cannot make the
# daemon allocate gigabytes: scrypt needs 128 * r * N bytes, bounded here at
# 256 MiB (twice what this module's own export uses).
_MAX_N, _MAX_R, _MAX_P = 2**20, 16, 4
_MAX_SCRYPT_BYTES = 256 * 1024 * 1024
_SOURCE = "<import>"


def key_fingerprint(key: bytes) -> str:
    """The short hash two machines compare; never the key."""
    return hashlib.sha256(key.strip()).hexdigest()[:12]


@dataclass(frozen=True)
class KeyFileInfo:
    """What a key file says about itself before it is opened."""

    fingerprint: str
    #: True for a ``.cfk`` backup, which needs its passphrase to open.
    protected: bool


def wrap(key: bytes, passphrase: str) -> str:
    """The ``.cfk`` text for ``key``, encrypted under ``passphrase``."""
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise MasterKeyPassphraseTooShort(MIN_PASSPHRASE_LENGTH)
    key = key.strip()
    salt = os.urandom(16)
    token = Fernet(_derive(passphrase, salt, _N, _R, _P)).encrypt(key)
    doc = {
        _FORMAT_KEY: _FORMAT_VERSION,
        "fingerprint": key_fingerprint(key),
        "kdf": {
            "name": "scrypt",
            "salt": base64.b64encode(salt).decode("ascii"),
            "n": _N,
            "r": _R,
            "p": _P,
        },
        "key": token.decode("ascii"),
    }
    return json.dumps(doc, indent=2) + "\n"


def peek(material: str) -> KeyFileInfo:
    """Whose key a file holds, without its passphrase."""
    text = material.strip()
    if not text:
        raise MasterKeyFileInvalid(_SOURCE, "no key material supplied")
    doc = _backup_doc(text)
    if doc is None:
        return KeyFileInfo(fingerprint=key_fingerprint(_bare_key(text)), protected=False)
    return KeyFileInfo(fingerprint=_header_fingerprint(doc), protected=True)


def unwrap(material: str, passphrase: str | None) -> bytes:
    """The master key a file holds, opened with ``passphrase`` when it needs one."""
    text = material.strip()
    if not text:
        raise MasterKeyFileInvalid(_SOURCE, "no key material supplied")
    doc = _backup_doc(text)
    if doc is None:
        return _bare_key(text)
    if not passphrase:
        raise MasterKeyPassphraseWrong()
    salt, n, r, p = _kdf_params(doc)
    try:
        key = Fernet(_derive(passphrase, salt, n, r, p)).decrypt(str(doc.get("key", "")).encode())
    except InvalidToken as e:
        raise MasterKeyPassphraseWrong() from e
    _bare_key(key.decode("ascii", errors="replace"))
    if key_fingerprint(key) != _header_fingerprint(doc):
        raise MasterKeyFileInvalid(_SOURCE, "the fingerprint in the file is not its key's")
    return key.strip()


def _derive(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    raw = Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _backup_doc(text: str) -> dict[str, Any] | None:
    """The parsed backup, or None when the text is not JSON at all (a bare key)."""
    if not text.startswith("{"):
        return None
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise MasterKeyFileInvalid(_SOURCE, "not a Coffer key file") from e
    if not isinstance(doc, dict) or doc.get(_FORMAT_KEY) != _FORMAT_VERSION:
        raise MasterKeyFileInvalid(_SOURCE, "not a Coffer key file this version reads")
    return doc


def _bare_key(text: str) -> bytes:
    raw = text.strip().encode("utf-8")
    try:
        Fernet(raw)
    except (ValueError, binascii.Error) as e:
        raise MasterKeyFileInvalid(_SOURCE, "not a valid Fernet key") from e
    return raw


def _header_fingerprint(doc: dict[str, Any]) -> str:
    fingerprint = doc.get("fingerprint")
    if not isinstance(fingerprint, str) or len(fingerprint) != 12:
        raise MasterKeyFileInvalid(_SOURCE, "the key file carries no fingerprint")
    return fingerprint.lower()


def _kdf_params(doc: dict[str, Any]) -> tuple[bytes, int, int, int]:
    kdf = doc.get("kdf")
    if not isinstance(kdf, dict) or kdf.get("name") != "scrypt":
        raise MasterKeyFileInvalid(_SOURCE, "unknown key derivation")
    try:
        salt = base64.b64decode(str(kdf["salt"]), validate=True)
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
    except (KeyError, TypeError, ValueError, binascii.Error) as e:
        raise MasterKeyFileInvalid(_SOURCE, "unreadable key derivation parameters") from e
    power_of_two = n > 1 and n & (n - 1) == 0
    in_range = power_of_two and n <= _MAX_N and 1 <= r <= _MAX_R and 1 <= p <= _MAX_P
    if not (in_range and salt and 128 * r * n <= _MAX_SCRYPT_BYTES):
        raise MasterKeyFileInvalid(_SOURCE, "key derivation parameters out of range")
    return salt, n, r, p
