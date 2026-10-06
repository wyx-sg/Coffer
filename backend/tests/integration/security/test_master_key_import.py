"""Importing another machine's master key (spec secret "Import a master key
after showing whose key it is"): previewed first, a protected backup opens
only with its passphrase, and the replaced key is never overwritten."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet

from coffer.application.secret.master_key_import import MasterKeyService
from coffer.domain.errors import CofferError
from coffer.infrastructure.secret import key_backup
from coffer.infrastructure.sync.master_key import ResolvedMasterKey, SecretFiles
from coffer.surfaces.http.secret_boundary_wiring import make_master_key_manager, master_key_path


class _Audit:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def record(self, event: str, **kw: Any) -> None:
        self.rows.append({"event": event, **kw})


class _Keys(MasterKeyService):
    def __init__(self, home: Path) -> None:
        key = ResolvedMasterKey(make_master_key_manager(home))
        super().__init__(
            master_key=key,
            secrets=SecretFiles(key, home=home),
            audit=_Audit(),  # type: ignore[arg-type]
        )


def _home_with_key(home: Path) -> bytes:
    key = Fernet.generate_key()
    path = master_key_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key)
    os.chmod(path, 0o600)
    return key


@pytest.mark.acceptance(
    spec="secret", scenario="an import shows whose key the file holds before replacing"
)
def test_a_preview_names_both_keys_and_changes_nothing(tmp_path: Path) -> None:
    own = _home_with_key(tmp_path)
    keys = _Keys(tmp_path)
    other = Fernet.generate_key()
    different = keys.preview_key(key_backup.wrap(other, "correct horse"))
    same = keys.preview_key(own.decode())
    assert different.protected is True and different.fingerprint != different.current
    assert same.protected is False and same.fingerprint == same.current
    assert keys._master_key.export_key() == own


@pytest.mark.acceptance(
    spec="secret", scenario="a protected key file opens only with its passphrase"
)
async def test_a_protected_backup_imports_only_with_its_passphrase(tmp_path: Path) -> None:
    own = _home_with_key(tmp_path)
    keys = _Keys(tmp_path)
    other = Fernet.generate_key()
    material = key_backup.wrap(other, "correct horse")
    for wrong in ("not it at all", None):
        with pytest.raises(CofferError) as caught:
            await keys.import_key(material, wrong)
        assert caught.value.code == "MASTER_KEY_PASSPHRASE_WRONG"
        assert keys._master_key.export_key() == own
    done = await keys.import_key(material, "correct horse")
    assert done.replaced is True
    assert keys._master_key.export_key() == other
