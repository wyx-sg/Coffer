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


@pytest.mark.acceptance(
    spec="vault-sync", scenario="logs and caches a skill's scripts write are not published"
)
def test_logs_and_caches_a_skills_scripts_write_are_never_recorded(
    writer: VaultWriter, repo: VaultRepository
) -> None:
    skill = repo.root / "skills/runner"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(b"---\nname: runner\n---\n")
    (skill / "scripts/run.mjs").write_bytes(b"console.log(1)\n")
    (skill / "run.log").write_bytes(b"started\n")
    for generated in ("node_modules/x/index.js", ".pytest_cache/v/cache/lastfailed"):
        (skill / generated).parent.mkdir(parents=True)
        (skill / generated).write_bytes(b"{}\n")
    writer.settle()
    assert set(repo.tree("HEAD", "skills")) == {
        "skills/runner/SKILL.md",
        "skills/runner/scripts/run.mjs",
    }
    assert writer.pending() == {}
