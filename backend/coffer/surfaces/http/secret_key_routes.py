"""/api/v1/secrets/key — this machine's master key: its fingerprint, a key file
previewed beside it, and installing one (spec secret "Import a master key after
showing whose key it is").

The key is the secret store's, so these routes sit under ``/secrets`` and answer
whether or not the experimental ``sync`` feature is on: Settings > Security
shows the fingerprint and offers the import either way.

No route returns the key. ``/key/import/preview`` says whose key a file holds
and changes nothing. ``/key/import`` installs one only against a presence grant
the desktop app signed for that key's fingerprint, redeemed before anything
changes, so a process that can reach the API cannot swap the key and then forge
grants with the key it chose. The command line cannot get such a grant: a
person imports with ``coffer secret import-key``, which opens the app.
"""

from __future__ import annotations

from fastapi import APIRouter

from coffer.application.secret.master_key_import import MasterKeyService
from coffer.surfaces.http.secret_boundary_wiring import get_presence_grants
from coffer.surfaces.http.secret_key_schemas import (
    KeyFingerprintOut,
    KeyImportIn,
    KeyImportOut,
    KeyMaterialIn,
    KeyPreviewOut,
)

#: Mounted inside the ``/api/v1/secrets`` router, which carries the token check.
router = APIRouter(prefix="/key")

_SERVICE: MasterKeyService | None = None


def set_master_key_service(service: MasterKeyService | None) -> None:
    global _SERVICE
    _SERVICE = service


def get_master_key_service() -> MasterKeyService:
    if _SERVICE is None:
        raise RuntimeError("master key service not initialised")
    return _SERVICE


@router.get("/fingerprint", response_model=KeyFingerprintOut)
async def key_fingerprint() -> KeyFingerprintOut:
    return KeyFingerprintOut(fingerprint=get_master_key_service().key_fingerprint())


@router.post("/import/preview", response_model=KeyPreviewOut)
async def preview_key_import(body: KeyMaterialIn) -> KeyPreviewOut:
    """Whose key a file holds and whether it is this machine's, changing nothing.

    A passphrase-protected backup is not opened here: its fingerprint is read
    from the file and checked against the key when it is imported.
    """
    preview = get_master_key_service().preview_key(body.material)
    return KeyPreviewOut(
        fingerprint=preview.fingerprint,
        current_fingerprint=preview.current,
        same=preview.fingerprint == preview.current,
        protected=preview.protected,
    )


@router.post("/import", response_model=KeyImportOut)
async def import_key(body: KeyImportIn) -> KeyImportOut:
    """Install a master key — only with a grant the desktop app signed for this
    exact key. Redeemed before anything changes."""
    service = get_master_key_service()
    fingerprint = service.preview_key(body.material).fingerprint
    get_presence_grants().redeem("import_master_key", fingerprint, body.nonce, body.signature)
    result = await service.import_key(body.material, body.passphrase, actor="desktop")
    return KeyImportOut(
        fingerprint=result.fingerprint,
        replaced=result.replaced,
        readable=result.readable,
        locked_refs=result.locked_refs,
    )


__all__ = ["get_master_key_service", "router", "set_master_key_service"]
