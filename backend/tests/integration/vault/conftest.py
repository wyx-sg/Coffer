from __future__ import annotations

from pathlib import Path

import pytest

from coffer.infrastructure.vault.repository import VaultRepository
from coffer.infrastructure.vault.writer import VaultWriter


@pytest.fixture
def repo(tmp_path: Path) -> VaultRepository:
    r = VaultRepository(tmp_path / "vault")
    r.ensure()
    return r


@pytest.fixture
def writer(repo: VaultRepository) -> VaultWriter:
    return VaultWriter(repo, machine=lambda: "machine-1")
