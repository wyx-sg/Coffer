"""What the vault repository never records, so no round can push it (spec
vault-sync "Skip symlinks and nested repositories")."""

from __future__ import annotations

import pytest

from coffer.infrastructure.vault.repository import VaultRepository
from coffer.infrastructure.vault.writer import VaultWriter


@pytest.mark.acceptance(
    spec="vault-sync", scenario="Python bytecode beside a skill's scripts is not published"
)
def test_bytecode_beside_a_skills_scripts_is_never_recorded(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    scripts = repo.root / "skills/pdf/scripts"
    (scripts / "__pycache__").mkdir(parents=True)
    (repo.root / "skills/pdf/SKILL.md").write_bytes(b"---\nname: pdf\n---\n")
    (scripts / "fill.py").write_bytes(b"print('fill')\n")
    (scripts / "__pycache__/fill.cpython-312.pyc").write_bytes(b"\x00bytecode")
    (scripts / "stray.pyo").write_bytes(b"\x00bytecode")
    writer.settle()
    assert set(repo.tree("HEAD", "skills")) == {
        "skills/pdf/SKILL.md",
        "skills/pdf/scripts/fill.py",
    }
    assert writer.pending() == {}
