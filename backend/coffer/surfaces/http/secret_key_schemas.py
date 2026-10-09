"""Wire shapes for /api/v1/secrets/key: this machine's master key fingerprint,
a key file previewed beside it, and installing one (spec secret "Import a master
key after showing whose key it is").

No shape carries the key: only 12-character fingerprints go out. The key file's
text and a backup's passphrase come in, and neither is stored or echoed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KeyFingerprintOut(BaseModel):
    fingerprint: str | None


class KeyMaterialIn(BaseModel):
    #: The key file's text as the person picked it: a ``.cfk`` backup or a
    #: bare key.
    material: str = Field(min_length=1)


class KeyPreviewOut(BaseModel):
    """A key file beside this machine's key, before anything is replaced."""

    #: The key in the file (12 hex characters, never the key).
    fingerprint: str
    #: This machine's key, or null when it holds none yet.
    current_fingerprint: str | None
    #: True when both are the same key, so importing changes nothing.
    same: bool
    #: True for a passphrase-protected ``.cfk`` backup.
    protected: bool


class KeyImportIn(BaseModel):
    material: str
    #: Opens a ``.cfk`` backup; not needed for a bare key. Never stored or
    #: recorded.
    passphrase: str | None = None
    #: The presence grant the desktop app signed for importing this key (spec
    #: secret "Release plaintext only to a present human in the desktop app").
    nonce: str = Field(min_length=8, max_length=128)
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")


class KeyImportOut(BaseModel):
    #: The key this machine now uses.
    fingerprint: str
    #: True when a different key was installed before (it is kept as a backup).
    replaced: bool
    #: How many stored secrets the key decrypts.
    readable: int
    #: The stored secrets it still cannot decrypt.
    locked_refs: list[str]


__all__ = [
    "KeyFingerprintOut",
    "KeyImportIn",
    "KeyImportOut",
    "KeyMaterialIn",
    "KeyPreviewOut",
]
