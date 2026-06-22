"""Unit tests for FileNativeMemoryScanner (spec 004).

Builds a temp ``projects/<slug>/memory`` tree on disk and asserts the scanner
reports one entry per project that HAS a memory subdir, with ``item_count``
counting ``*.md`` files excluding the ``MEMORY.md`` index.
"""

from __future__ import annotations

import pathlib

from coffer.infrastructure.agent.native_memory_store import FileNativeMemoryScanner


def _write(p: pathlib.Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_scan_counts_md_files_excluding_index(tmp_path: pathlib.Path) -> None:
    projects = tmp_path / "projects"
    # -A-B has 2 facts + the index; -C has 1 fact.
    _write(projects / "-A-B" / "memory" / "MEMORY.md")
    _write(projects / "-A-B" / "memory" / "x.md")
    _write(projects / "-A-B" / "memory" / "y.md")
    _write(projects / "-C" / "memory" / "z.md")
    # -D has no memory subdir -> excluded entirely.
    (projects / "-D").mkdir(parents=True)

    out = FileNativeMemoryScanner().scan(projects, "memory")

    by_slug = {s.slug: s for s in out}
    assert set(by_slug) == {"-A-B", "-C"}
    assert by_slug["-A-B"].item_count == 2
    assert by_slug["-C"].item_count == 1
    # memory_dir is the absolute dir path.
    assert by_slug["-A-B"].memory_dir == str(projects / "-A-B" / "memory")
    assert by_slug["-C"].memory_dir == str(projects / "-C" / "memory")
    # No session log present -> real project_path is unknown.
    assert by_slug["-A-B"].project_path is None


def test_scan_reads_real_project_path_from_session_cwd(tmp_path: pathlib.Path) -> None:
    """The slug encoding is lossy (``.``/``_``/``/`` all collapse to ``-``), so
    the real project dir is recovered from a session log's ``cwd`` instead."""
    import json

    projects = tmp_path / "projects"
    slug = "-Users-yuxing-wu-WorkEnv-account-gateway"
    _write(projects / slug / "memory" / "a.md")
    # A session transcript records the true working directory per line.
    session = projects / slug / "0bf876fa.jsonl"
    session.write_text(
        json.dumps({"type": "summary"})
        + "\n"
        + json.dumps({"cwd": "/Users/yuxing.wu/WorkEnv/account-gateway"})
        + "\n",
        encoding="utf-8",
    )

    out = FileNativeMemoryScanner().scan(projects, "memory")
    assert out[0].project_path == "/Users/yuxing.wu/WorkEnv/account-gateway"


def test_scan_missing_projects_root_returns_empty(tmp_path: pathlib.Path) -> None:
    assert FileNativeMemoryScanner().scan(tmp_path / "nope", "memory") == []


def test_scan_projects_root_is_a_file_returns_empty(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "projects"
    f.write_text("not a dir", encoding="utf-8")
    assert FileNativeMemoryScanner().scan(f, "memory") == []


def test_scan_skips_non_directory_entries(tmp_path: pathlib.Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    # A stray file directly under projects/ is not a project dir -> skipped.
    (projects / "stray.txt").write_text("x", encoding="utf-8")
    _write(projects / "-A" / "memory" / "a.md")

    out = FileNativeMemoryScanner().scan(projects, "memory")
    assert [s.slug for s in out] == ["-A"]


def test_scan_empty_memory_dir_counts_zero(tmp_path: pathlib.Path) -> None:
    projects = tmp_path / "projects"
    # memory dir present but only the index lives there -> count 0, still listed.
    _write(projects / "-A" / "memory" / "MEMORY.md")

    out = FileNativeMemoryScanner().scan(projects, "memory")
    assert out and out[0].slug == "-A"
    assert out[0].item_count == 0
