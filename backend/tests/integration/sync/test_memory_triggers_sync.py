"""The vault carries authored memory triggers like any other file tree (spec
vault-sync "Apply knowledge, skill and memory-trigger file changes").

Triggers are authored content (spec memory "Keep triggers in the vault, armed
only by a person"), so a round publishes ``vault/memory-triggers/`` under the
bundle's ``memory-triggers/`` and applies an arriving or deleted trigger file.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.sync.appliers import TreeApplier
from coffer.domain.sync.diff import area_of
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.paths import memory_triggers_root, mirrored_trees

_TRIGGER = """---
id: node20-abc123
note: coffer/node20
kind: block
command: make\\b.*\\bverify
unless: v20
error: ''
armed_by: me
armed_at: '2026-09-30T00:00:00+00:00'
proposed_by: ''
created: '2026-09-30T00:00:00+00:00'
---
"""


@pytest.fixture
def roots(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "roots" / "knowledge"))
    monkeypatch.setenv("COFFER_SKILLS_ROOT", str(tmp_path / "roots" / "skills"))
    monkeypatch.setenv("COFFER_MEMORY_TRIGGERS_ROOT", str(tmp_path / "roots" / "triggers"))
    return tmp_path


def test_memory_triggers_are_a_mirrored_tree_of_their_own_area(roots: pathlib.Path) -> None:
    assert ("memory-triggers", memory_triggers_root()) in mirrored_trees()
    assert memory_triggers_root() == roots / "roots" / "triggers"
    assert area_of("memory-triggers/node20-abc123.md") == "memory-triggers"


def test_the_default_root_is_in_the_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COFFER_MEMORY_TRIGGERS_ROOT", raising=False)
    root = memory_triggers_root()
    assert root.parts[-3:] == (".coffer", "vault", "memory-triggers")


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an arriving memory trigger is written into the vault"
)
async def test_an_arriving_trigger_is_written_and_a_deleted_one_removed(
    roots: pathlib.Path,
) -> None:
    live = memory_triggers_root()
    live.mkdir(parents=True)
    (live / "old-000000.md").write_text(_TRIGGER.replace("node20-abc123", "old-000000"))
    worktree = roots / "worktree"
    staged = worktree / "memory-triggers" / "node20-abc123.md"
    staged.parent.mkdir(parents=True)
    staged.write_text(_TRIGGER, encoding="utf-8")

    applier = TreeApplier("memory-triggers/", worktree=worktree, live_root=live)
    await applier.upsert("memory-triggers/node20-abc123.md")
    await applier.remove("memory-triggers/old-000000.md")

    assert (live / "node20-abc123.md").read_text(encoding="utf-8") == _TRIGGER
    assert not (live / "old-000000.md").exists()


@pytest.mark.acceptance(
    spec="vault-sync", scenario="an arriving memory trigger is written into the vault"
)
def test_a_published_bundle_carries_every_trigger_file(roots: pathlib.Path) -> None:
    live = memory_triggers_root()
    live.mkdir(parents=True)
    (live / "node20-abc123.md").write_text(_TRIGGER, encoding="utf-8")
    (roots / "roots" / "knowledge").mkdir(parents=True)
    (roots / "roots" / "skills").mkdir(parents=True)

    bundle = Bundle(roots / "bundle")
    bundle.mirror_trees_out()

    published = roots / "bundle" / "memory-triggers" / "node20-abc123.md"
    assert published.read_text(encoding="utf-8") == _TRIGGER
