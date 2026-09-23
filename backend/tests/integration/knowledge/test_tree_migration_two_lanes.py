"""Migration 0085's on-disk rewrite, against a real tree (spec knowledge FR-042/071).

The corpus is the user's own writing and this pass moves every file in it, so
the assertions below are about the FILES, not about a report: a fixture tree in
the shape a 0066-era vault actually has, the pass run over it, and then the
directory walked to see where everything landed.

``COFFER_KNOWLEDGE_ROOT`` is pinned into ``tmp_path`` by every test here. It is
also pinned by the root conftest, twice over — but this module is the one that
would do real damage if it were not, because ``migrate`` moves and deletes
rather than merely writing.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.infrastructure.persistence.migrations import knowledge_tree_0085 as tree


def _write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A knowledge root in the pre-0085 shape, with every case in one tree."""
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))

    collection = root / "shopee"
    _write(collection / "README.md", "# shopee\n\nInternal knowledge.\n")
    _write(collection / "account-service.md", "---\ntitle: Account\n---\n\nbody\n")
    _write(collection / "platforms" / "datasuite.md", "---\ntitle: DataSuite\n---\n\nbody\n")
    _write(collection / "platforms" / "deep" / "smart.md", "---\ntitle: Smart\n---\n\nbody\n")
    _write(collection / ".raw" / "handbook.pdf", "%PDF-fake")
    _write(collection / ".raw" / "decks" / "q3.pptx", "fake-pptx")
    # An original whose extracted Markdown already owns the name it wants.
    _write(collection / "account-service.md.orig", "original bytes")
    _write(collection / ".raw" / "account-service.md", "the original markdown upload")
    _write(collection / ".history" / "account-service.md", "what a rewrite replaced")

    # A second collection with nothing to move: it must still get both lanes.
    _write(root / "coffer" / "README.md", "# coffer\n\nThe project's own notes.\n")
    return root


def _tree(root: pathlib.Path) -> set[str]:
    """Every path under ``root``, relative and posix, directories included."""
    return {str(p.relative_to(root).as_posix()) for p in root.rglob("*")}


def test_content_files_move_into_sources_keeping_their_nesting(root: pathlib.Path) -> None:
    tree.migrate()

    sources = root / "shopee" / "sources"
    assert (sources / "account-service.md").read_text() == "---\ntitle: Account\n---\n\nbody\n"
    # The folders a person made are their organisation of the material (FR-004).
    assert (sources / "platforms" / "datasuite.md").is_file()
    assert (sources / "platforms" / "deep" / "smart.md").is_file()
    # And nothing is left behind at the collection root.
    assert not (root / "shopee" / "account-service.md").exists()
    assert not (root / "shopee" / "platforms").exists()


def test_raw_originals_become_visible_sources_under_their_own_names(root: pathlib.Path) -> None:
    tree.migrate()

    sources = root / "shopee" / "sources"
    assert (sources / "handbook.pdf").read_text() == "%PDF-fake"
    assert (sources / "decks" / "q3.pptx").read_text() == "fake-pptx"


def test_a_colliding_original_is_suffixed_not_written_over(root: pathlib.Path) -> None:
    tree.migrate()

    sources = root / "shopee" / "sources"
    # The content file keeps the name someone has been reading it under...
    assert (sources / "account-service.md").read_text().startswith("---\ntitle: Account")
    # ...and the original that wanted it takes the suffix, with its bytes intact.
    assert (sources / "account-service-2.md").read_text() == "the original markdown upload"


def test_the_hidden_directories_are_gone(root: pathlib.Path) -> None:
    tree.migrate()

    assert not (root / "shopee" / ".raw").exists()
    assert not (root / "shopee" / ".history").exists()
    # .history/ is deleted with whatever it held; nothing of it reaches sources/.
    assert "what a rewrite replaced" not in {
        p.read_text() for p in (root / "shopee" / "sources").rglob("*") if p.is_file()
    }


def test_the_collection_readme_stays_at_the_collection_root(root: pathlib.Path) -> None:
    tree.migrate()

    assert (root / "shopee" / "README.md").read_text().startswith("# shopee")
    assert not (root / "shopee" / "sources" / "README.md").exists()


def test_topics_exists_and_is_empty_for_every_collection(root: pathlib.Path) -> None:
    tree.migrate()

    for collection in ("shopee", "coffer"):
        topics = root / collection / "topics"
        assert topics.is_dir(), f"{collection} has no topics/ lane"
        assert list(topics.iterdir()) == [], "topics/ is curation's to fill, not the migration's"


def test_a_collection_with_nothing_to_move_still_gets_both_lanes(root: pathlib.Path) -> None:
    tree.migrate()

    assert (root / "coffer" / "sources").is_dir()
    assert (root / "coffer" / "topics").is_dir()
    assert (root / "coffer" / "README.md").is_file()


def test_the_root_is_backed_up_before_anything_moves(root: pathlib.Path) -> None:
    report = tree.migrate()

    backup = root.parent / f"knowledge{tree.BACKUP_SUFFIX}"
    assert report.backup == str(backup)
    # The backup is the tree as it was: hidden lanes, flat content and all.
    assert (backup / "shopee" / "account-service.md").is_file()
    assert (backup / "shopee" / ".raw" / "handbook.pdf").is_file()
    assert (backup / "shopee" / ".history" / "account-service.md").is_file()
    assert not (backup / "shopee" / "sources").exists()


def test_running_twice_changes_nothing(root: pathlib.Path) -> None:
    tree.migrate()
    after_first = _tree(root)
    contents = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    backup = root.parent / f"knowledge{tree.BACKUP_SUFFIX}"
    backup_before = {str(p.relative_to(backup)) for p in backup.rglob("*")}

    second = tree.migrate()

    assert _tree(root) == after_first
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == contents
    assert second.sources_moved == 0
    assert second.originals_revealed == 0
    assert second.lanes_created == 0
    # And no second backup: by now the root is already rewritten, so copying
    # over it would replace the only pre-migration copy with a post-one.
    assert {str(p.relative_to(backup)) for p in backup.rglob("*")} == backup_before


def test_no_backup_is_taken_when_there_is_nothing_to_rewrite(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    _write(root / "coffer" / "README.md", "# coffer\n")
    (root / "coffer" / "sources").mkdir()
    (root / "coffer" / "topics").mkdir()

    report = tree.migrate()

    assert report.backup == ""
    assert not (root.parent / f"knowledge{tree.BACKUP_SUFFIX}").exists()


def test_the_retired_shared_skill_master_is_removed(
    root: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    master_root = tmp_path / "skills"
    _write(master_root / "coffer-knowledge" / "SKILL.md", "the old shared master")
    _write(master_root / "coffer-datasuite" / "SKILL.md", "someone else's skill")

    tree.migrate(master_root=master_root)

    assert not (master_root / "coffer-knowledge").exists()
    assert (master_root / "coffer-datasuite" / "SKILL.md").is_file()
