"""Unit coverage for native-memory import helpers (spec 004).

``read_memory_facts`` parses a Claude Code per-project memory dir into
``ParsedNativeFact`` rows (skipping the ``MEMORY.md`` index and any unparseable
file); ``resolve_project_path`` recovers the REAL project path for a memory dir,
preferring an existing decoded slug dir, falling back to a sibling transcript's
``cwd``, and returning ``None`` when neither resolves.
"""

from __future__ import annotations

import json
import pathlib

from coffer.domain.agent.native_memory import decode_project_slug
from coffer.infrastructure.agent.native_memory_import import (
    ParsedNativeFact,
    read_memory_facts,
    resolve_project_path,
)


def _write_fact(
    mem: pathlib.Path,
    filename: str,
    *,
    name: str | None = None,
    description: str | None = None,
    origin: str | None = None,
    body: str = "body text",
) -> None:
    lines = ["---"]
    if name is not None:
        lines.append(f"name: {name}")
    if description is not None:
        lines.append(f"description: {description}")
    if origin is not None:
        lines.append(f"originSessionId: {origin}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    (mem / filename).write_text("\n".join(lines), encoding="utf-8")


def test_read_memory_facts_parses_and_skips_index(tmp_path: pathlib.Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fact(
        mem,
        "a.md",
        name="Alpha fact",
        description="alpha desc",
        origin="sess-1",
        body="alpha body",
    )
    _write_fact(mem, "b.md", description="beta desc", body="beta body")  # no name → stem
    (mem / "MEMORY.md").write_text("---\nname: index\n---\nindex", encoding="utf-8")

    facts = read_memory_facts(mem)

    assert isinstance(facts[0], ParsedNativeFact)
    by_name = {f.name: f for f in facts}
    # MEMORY.md is excluded.
    assert "index" not in by_name
    assert len(facts) == 2

    alpha = by_name["Alpha fact"]
    assert alpha.description == "alpha desc"
    assert alpha.origin_session_id == "sess-1"
    assert alpha.body == "alpha body"

    # b.md has no `name` → fall back to filename stem; missing origin → None.
    beta = by_name["b"]
    assert beta.description == "beta desc"
    assert beta.origin_session_id is None
    assert beta.body == "beta body"


def test_read_memory_facts_skips_unparseable_defensively(tmp_path: pathlib.Path) -> None:
    mem = tmp_path / "memory"
    mem.mkdir()
    _write_fact(mem, "good.md", name="Good", body="ok")
    # A file with malformed YAML frontmatter must not crash the scan; the
    # frontmatter splitter degrades to ({}, body) → name falls back to stem.
    (mem / "bad.md").write_text("---\nname: : : broken\n---\nbad body", encoding="utf-8")

    facts = read_memory_facts(mem)
    names = {f.name for f in facts}
    assert "Good" in names
    assert "bad" in names  # stem fallback, never raised


def test_read_memory_facts_empty_when_no_dir(tmp_path: pathlib.Path) -> None:
    assert read_memory_facts(tmp_path / "missing" / "memory") == []


def test_resolve_project_path_prefers_existing_decoded_dir(tmp_path: pathlib.Path) -> None:
    # The decode is lossy at any '-' in a path segment, so the slug only
    # round-trips when the decoded path has none. Decode a known dash-free slug,
    # create exactly that dir on disk, and assert it is preferred over any jsonl.
    slug = "-tmp-coffer_slugtest_realproj"
    _, decoded = decode_project_slug(slug)
    assert decoded is not None
    real = pathlib.Path(decoded)
    real.mkdir(parents=True, exist_ok=True)
    try:
        mem = tmp_path / "projects" / slug / "memory"
        mem.mkdir(parents=True)
        # A sibling jsonl that would resolve differently — must be ignored,
        # because the decoded dir exists (step 1 wins over step 2).
        (mem.parent / "t.jsonl").write_text(
            json.dumps({"cwd": "/should/not/win"}), encoding="utf-8"
        )

        assert resolve_project_path(mem) == decoded
    finally:
        real.rmdir()


def test_resolve_project_path_falls_back_to_jsonl_cwd(tmp_path: pathlib.Path) -> None:
    # Decoded slug points at a non-existent dir → read sibling *.jsonl for "cwd".
    slug = "-no-such-decoded-path-xyz"
    project_dir = tmp_path / "projects" / slug
    mem = project_dir / "memory"
    mem.mkdir(parents=True)
    real_cwd = str(tmp_path / "real" / "project")
    lines = [
        "not json at all",
        json.dumps({"type": "user", "noCwd": True}),
        json.dumps({"cwd": real_cwd, "sessionId": "s1"}),
    ]
    (project_dir / "transcript.jsonl").write_text("\n".join(lines), encoding="utf-8")

    assert resolve_project_path(mem) == real_cwd


def test_resolve_project_path_none_when_unresolvable(tmp_path: pathlib.Path) -> None:
    slug = "-no-such-decoded-path-xyz"
    project_dir = tmp_path / "projects" / slug
    mem = project_dir / "memory"
    mem.mkdir(parents=True)
    # No jsonl, decoded path absent → None.
    assert resolve_project_path(mem) is None
