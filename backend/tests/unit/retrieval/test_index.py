"""Unit tests for the disposable retrieval sidecar (infrastructure/retrieval/index.py).

Every test pins ``COFFER_INDEX_ROOT`` at ``tmp_path`` so nothing here can ever
touch a real ``~/.coffer/index`` — a past bug let a knowledge-layer test do
exactly that to the live vault.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.domain.knowledge.retrieval import IndexedSection
from coffer.infrastructure.retrieval import index as index_module
from coffer.infrastructure.retrieval.index import (
    FORMAT_VERSION,
    INDEX_ROOT_ENV,
    FileStamp,
    SidecarIndex,
    index_path,
    index_root,
    stamp_file,
)


@pytest.fixture(autouse=True)
def _pin_index_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    root = tmp_path / "index-root"
    monkeypatch.setenv(INDEX_ROOT_ENV, str(root))
    return root


# ---------------------------------------------------------------------------
# index_root / index_path
# ---------------------------------------------------------------------------


def test_index_root_honors_env_override(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "somewhere-else"
    monkeypatch.setenv(INDEX_ROOT_ENV, str(custom))
    assert index_root() == custom


def test_index_path_is_single_file_inside_index_root() -> None:
    path = index_path()
    assert path.parent == index_root()
    assert path.suffix == ".ndjson"


# ---------------------------------------------------------------------------
# stamp_file
# ---------------------------------------------------------------------------


def test_stamp_file_reflects_size_and_content(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "a.md"
    f.write_text("hello world", encoding="utf-8")
    stamp = stamp_file("a.md", f)
    assert stamp.path == "a.md"
    assert stamp.size == len("hello world")
    assert stamp.mtime_ns == f.stat().st_mtime_ns
    assert len(stamp.digest) == 64  # sha256 hex


def test_stamp_file_digest_changes_with_content(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "a.md"
    f.write_text("version one", encoding="utf-8")
    first = stamp_file("a.md", f)
    f.write_text("version two, longer", encoding="utf-8")
    second = stamp_file("a.md", f)
    assert first.digest != second.digest
    assert first.size != second.size


# ---------------------------------------------------------------------------
# SidecarIndex: round-trip, freshness, mutation
# ---------------------------------------------------------------------------


def _stamp(path: str, size: int = 1, mtime_ns: int = 1, digest: str = "d") -> FileStamp:
    return FileStamp(path=path, size=size, mtime_ns=mtime_ns, digest=digest)


def _sections(path: str) -> list[IndexedSection]:
    return [
        IndexedSection(path=path, heading="H1", start_line=1, vector=(0.1, 0.2, 0.3)),
        IndexedSection(path=path, heading="H2", start_line=10, vector=(0.4, 0.5, 0.6)),
    ]


def test_load_missing_file_returns_empty_index() -> None:
    idx = SidecarIndex.load()
    assert idx.is_empty()
    assert idx.sections() == ()
    assert idx.indexed_paths() == frozenset()


def test_save_then_load_round_trips_sections_and_stamps() -> None:
    idx = SidecarIndex()
    stamp = _stamp("a.md")
    sections = _sections("a.md")
    idx.replace_file(stamp, sections)
    idx.save()

    loaded = SidecarIndex.load()
    assert loaded.stamp_of("a.md") == stamp
    assert set(loaded.sections()) == set(sections)
    assert loaded.indexed_paths() == frozenset({"a.md"})
    assert not loaded.is_empty()


def test_save_creates_index_root_directory_if_absent() -> None:
    assert not index_root().exists()
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    idx.save()
    assert index_path().is_file()


def test_load_empty_file_returns_empty_index() -> None:
    index_root().mkdir(parents=True)
    index_path().write_text("", encoding="utf-8")
    idx = SidecarIndex.load()
    assert idx.is_empty()


def test_load_corrupt_file_returns_empty_index_not_raise() -> None:
    index_root().mkdir(parents=True)
    index_path().write_text("this is not json at all {{{", encoding="utf-8")
    idx = SidecarIndex.load()
    assert idx.is_empty()


def test_load_unknown_format_version_discards_rather_than_misreads() -> None:
    index_root().mkdir(parents=True)
    index_path().write_text('{"format_version": 999}\n{"path": "a.md"}\n', encoding="utf-8")
    idx = SidecarIndex.load()
    assert idx.is_empty()


def test_load_truncated_trailing_line_keeps_earlier_complete_records() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    idx.save()
    # Simulate a process killed mid-write: append a truncated JSON line.
    with index_path().open("a", encoding="utf-8") as fh:
        fh.write('{"path": "b.md", "size": 1, "mtime_')  # cut off mid-value

    loaded = SidecarIndex.load()
    assert loaded.indexed_paths() == frozenset({"a.md"})
    assert loaded.stamp_of("b.md") is None


def test_load_line_missing_required_field_is_skipped_not_raise() -> None:
    index_root().mkdir(parents=True)
    header = f'{{"format_version": {FORMAT_VERSION}}}'
    bad_record = '{"path": "a.md", "size": 1}'  # missing mtime_ns / digest / sections
    index_path().write_text(f"{header}\n{bad_record}\n", encoding="utf-8")
    idx = SidecarIndex.load()
    assert idx.is_empty()


def test_is_fresh_true_when_stamp_matches() -> None:
    idx = SidecarIndex()
    stamp = _stamp("a.md")
    idx.replace_file(stamp, _sections("a.md"))
    assert idx.is_fresh(stamp) is True


def test_is_fresh_false_when_size_changes() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md", size=1), _sections("a.md"))
    assert idx.is_fresh(_stamp("a.md", size=2)) is False


def test_is_fresh_false_when_mtime_changes() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md", mtime_ns=1), _sections("a.md"))
    assert idx.is_fresh(_stamp("a.md", mtime_ns=2)) is False


def test_is_fresh_false_when_digest_changes() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md", digest="d1"), _sections("a.md"))
    assert idx.is_fresh(_stamp("a.md", digest="d2")) is False


def test_is_fresh_false_when_path_never_indexed() -> None:
    idx = SidecarIndex()
    assert idx.is_fresh(_stamp("never.md")) is False


def test_replace_file_overwrites_prior_sections_for_same_path() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md", digest="old"), _sections("a.md"))
    new_sections = [IndexedSection(path="a.md", heading="New", start_line=1, vector=(1.0,))]
    idx.replace_file(_stamp("a.md", digest="new"), new_sections)
    assert idx.sections() == tuple(new_sections)
    assert idx.stamp_of("a.md") == _stamp("a.md", digest="new")


def test_drop_removes_a_file_and_is_noop_if_absent() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    idx.drop("a.md")
    assert idx.stamp_of("a.md") is None
    idx.drop("never-there.md")  # must not raise


def test_retain_prunes_files_no_longer_present() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    idx.replace_file(_stamp("b.md"), _sections("b.md"))
    idx.replace_file(_stamp("c.md"), _sections("c.md"))
    idx.retain(["a.md", "c.md"])
    assert idx.indexed_paths() == frozenset({"a.md", "c.md"})


def test_sections_combines_across_all_indexed_files() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    idx.replace_file(_stamp("b.md"), _sections("b.md"))
    all_sections = idx.sections()
    assert len(all_sections) == 4
    assert {s.path for s in all_sections} == {"a.md", "b.md"}


def test_is_empty_reflects_record_count() -> None:
    idx = SidecarIndex()
    assert idx.is_empty() is True
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    assert idx.is_empty() is False


def test_atomic_save_leaves_no_partial_or_temp_file_behind() -> None:
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    idx.save()
    leftovers = list(index_root().glob("*.tmp"))
    assert leftovers == []
    idx.replace_file(_stamp("b.md"), _sections("b.md"))
    idx.save()
    leftovers = list(index_root().glob("*.tmp"))
    assert leftovers == []
    assert index_path().is_file()


def test_save_is_atomic_via_replace_not_in_place_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """save() must write to a temp path and Path.replace it — never write the
    target file in place, which could leave a truncated file readable mid-write."""
    idx = SidecarIndex()
    idx.replace_file(_stamp("a.md"), _sections("a.md"))

    seen_replace_calls: list[pathlib.Path] = []
    original_replace = pathlib.Path.replace

    def _tracking_replace(self: pathlib.Path, target: pathlib.Path) -> pathlib.Path:
        seen_replace_calls.append(self)
        return original_replace(self, target)

    monkeypatch.setattr(pathlib.Path, "replace", _tracking_replace)
    idx.save()
    assert len(seen_replace_calls) == 1
    assert seen_replace_calls[0] != index_path()  # replaced FROM a temp path


def test_index_module_constants_exposed() -> None:
    assert index_module.INDEX_ROOT_ENV == "COFFER_INDEX_ROOT"
    assert isinstance(index_module.FORMAT_VERSION, int)


# ---------------------------------------------------------------------------
# namespacing (spec memory FR-052: knowledge and memory share this substrate,
# each under their own file so a rebuild of one never discards the other's)
# ---------------------------------------------------------------------------


def test_default_namespace_keeps_the_original_bare_filename() -> None:
    """Backward compatibility: an installation (or test) that never names a
    namespace gets exactly the file it always got."""
    assert index_path().name == "sidecar.ndjson"
    assert index_path("knowledge").name == "sidecar.ndjson"


def test_a_different_namespace_gets_its_own_file() -> None:
    assert index_path("memory") != index_path("knowledge")
    assert index_path("memory").parent == index_root()
    assert index_path("memory").name != index_path().name


def test_two_namespaces_do_not_share_records() -> None:
    knowledge_idx = SidecarIndex(namespace="knowledge")
    knowledge_idx.replace_file(_stamp("a.md"), _sections("a.md"))
    knowledge_idx.save()

    memory_idx = SidecarIndex(namespace="memory")
    memory_idx.replace_file(_stamp("b.md"), _sections("b.md"))
    memory_idx.save()

    assert SidecarIndex.load("knowledge").indexed_paths() == frozenset({"a.md"})
    assert SidecarIndex.load("memory").indexed_paths() == frozenset({"b.md"})


def test_rebuilding_one_namespace_does_not_touch_the_other() -> None:
    knowledge_idx = SidecarIndex(namespace="knowledge")
    knowledge_idx.replace_file(_stamp("a.md"), _sections("a.md"))
    knowledge_idx.save()

    # A brand-new memory-namespace index, saved once, must not disturb the
    # knowledge file that already exists on disk.
    memory_idx = SidecarIndex(namespace="memory")
    memory_idx.save()

    assert SidecarIndex.load("knowledge").indexed_paths() == frozenset({"a.md"})


def test_save_writes_back_to_the_namespace_it_was_loaded_for() -> None:
    idx = SidecarIndex(namespace="memory")
    idx.replace_file(_stamp("a.md"), _sections("a.md"))
    idx.save()

    loaded = SidecarIndex.load("memory")
    assert not index_path("knowledge").exists()
    assert index_path("memory").is_file()
    assert loaded.indexed_paths() == frozenset({"a.md"})
