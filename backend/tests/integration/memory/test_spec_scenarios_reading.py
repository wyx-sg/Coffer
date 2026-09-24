"""Acceptance scenarios for the reading half of the memory layer.

Real readers over fixture config directories under ``tmp_path``, real git
repositories, the real store under the suite-pinned ``COFFER_MEMORY_ROOT``.
``ResourceService``/``AuditService`` stay fakes: nothing asserted here is about
a database.
"""

from __future__ import annotations

import pathlib
import shutil
from datetime import datetime

import pytest

from coffer.application.memory.context import compose_context
from coffer.application.memory.recall import RecallService
from coffer.application.memory.service import DEFAULT_READERS, KIND_MEMORY, MemoryService
from coffer.infrastructure.memory import paths, store
from coffer.infrastructure.memory.raw_store import list_raw_entries, read_raw_entry
from coffer.infrastructure.memory.readers import ClaudeCodeMemoryReader, CodexMemoryReader
from tests.integration.memory.conftest import (
    FakeAudit,
    FakeResources,
    agent_source_resolver,
    claude_code_config,
    codex_config,
    init_repository,
)


def _cc_file(name: str, description: str, type_: str, body: str) -> str:
    return (
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  node_type: memory\n  type: {type_}\n---\n\n{body}\n"
    )


def _service(resources: FakeResources) -> MemoryService:
    return MemoryService(
        resources=resources,  # type: ignore[arg-type]
        audit=FakeAudit(),  # type: ignore[arg-type]
        agent_source_resolver=agent_source_resolver,
        readers={"claude_code": ClaudeCodeMemoryReader(), "codex": CodexMemoryReader()},
    )


def _all_raw() -> list:  # type: ignore[type-arg]
    return [e for p in store.list_partitions() for e in list_raw_entries(p)]


# --- Read only registered and enabled agents' memory -------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="read nothing from a disabled or unregistered agent"
)
async def test_only_the_enabled_registered_agents_memory_is_read(tmp_path: pathlib.Path) -> None:
    repository = init_repository(tmp_path / "home" / "dev" / "coffer")
    enabled_dir = claude_code_config(
        tmp_path / "enabled-claude",
        repository,
        {"enabled-fact.md": _cc_file("enabled-fact", "from the enabled agent", "project", "E")},
    )
    disabled_dir = claude_code_config(
        tmp_path / "disabled-claude",
        repository,
        {"disabled-fact.md": _cc_file("disabled-fact", "from the disabled one", "project", "D")},
    )
    unregistered_dir = claude_code_config(
        tmp_path / "stray-claude",
        repository,
        {"stray-fact.md": _cc_file("stray-fact", "from nobody's directory", "project", "S")},
    )

    resources = FakeResources()
    resources.add_agent("enabled-cc", "claude_code", str(enabled_dir))
    resources.add_agent("disabled-cc", "claude_code", str(disabled_dir), enabled=False)

    result = await _service(resources).aggregate()

    entries = _all_raw()
    assert entries, "the enabled agent's memory was read"
    assert result.failures == ()
    assert {e.agent for e in entries} == {"enabled-cc"}
    assert {e.entry.title for e in entries} == {"enabled-fact"}
    native = {e.native_path for e in entries}
    assert all(p.startswith(str(enabled_dir)) for p in native)
    assert not any(p.startswith(str(disabled_dir)) for p in native)
    assert not any(p.startswith(str(unregistered_dir)) for p in native)


# --- Read no transcripts or rollouts -----------------------------------------


@pytest.mark.acceptance(spec="memory", scenario="list no transcript or rollout as a source")
def test_neither_reader_lists_a_transcript_rollout_or_raw_capture(tmp_path: pathlib.Path) -> None:
    project_root = tmp_path / "home" / "dev" / "coffer"
    claude_dir = claude_code_config(
        tmp_path / "claude",
        project_root,
        {"fact.md": _cc_file("fact", "a fact", "project", "body")},
    )
    project_dir = next((claude_dir / "projects").iterdir())
    # A session transcript beside the project's memory directory (the fixture
    # helper already writes one; add a UUID-named one as Claude Code does).
    (project_dir / "0b7c2d1e-aaaa-bbbb-cccc-000000000000.jsonl").write_text(
        '{"type":"user","cwd":"/x"}\n', encoding="utf-8"
    )
    assert any(p.suffix == ".jsonl" for p in project_dir.iterdir())

    codex_dir = codex_config(tmp_path / "codex", "# Task Group: g\n", "v1\n")
    rollouts = codex_dir / "sessions" / "2026" / "09" / "01"
    rollouts.mkdir(parents=True)
    (rollouts / "rollout-2026-09-01T10-00-00-abc.jsonl").write_text("{}\n", encoding="utf-8")
    (codex_dir / "memories" / "rollout_summaries").mkdir()
    (codex_dir / "memories" / "rollout_summaries" / "rollout-1.md").write_text(
        "summary\n", encoding="utf-8"
    )
    (codex_dir / "memories" / "raw_memories.md").write_text("raw capture\n", encoding="utf-8")

    cc_sources = [pathlib.Path(s.path) for s in ClaudeCodeMemoryReader().sources(str(claude_dir))]
    codex_sources = [pathlib.Path(s.path) for s in CodexMemoryReader().sources(str(codex_dir))]

    assert cc_sources == [project_dir / "memory" / "fact.md"]
    assert sorted(p.name for p in codex_sources) == ["MEMORY.md", "memory_summary.md"]
    for source in cc_sources + codex_sources:
        assert source.suffix != ".jsonl"
        assert "rollout" not in source.name
        assert "rollout_summaries" not in source.parts
        assert "sessions" not in source.relative_to(tmp_path).parts
        assert source.name != "raw_memories.md"


# --- Let only aggregation write raw entries ----------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="stamp a raw entry with its agent, native path and read time"
)
async def test_a_raw_entry_names_its_agent_path_and_read_time_and_is_reproducible(
    tmp_path: pathlib.Path,
) -> None:
    repository = init_repository(tmp_path / "home" / "dev" / "coffer")
    claude_dir = claude_code_config(
        tmp_path / "claude",
        repository,
        {
            "python-lockfile.md": _cc_file(
                "python-lockfile", "Dependencies are locked with uv", "project", "Run uv sync."
            )
        },
    )
    fact_path = str(next((claude_dir / "projects").iterdir()) / "memory" / "python-lockfile.md")
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", str(claude_dir))

    await _service(resources).aggregate()
    (first,) = list_raw_entries("coffer")
    stored = read_raw_entry("coffer", first.entry_id)

    assert stored.agent == "claude-code"
    assert stored.native_path == fact_path
    assert stored.captured_at  # the read time
    # ISO-8601 with a timezone: a time, not an opaque token.
    assert datetime.fromisoformat(stored.captured_at).tzinfo is not None

    shutil.rmtree(paths.raw_dir("coffer"))
    await _service(resources).aggregate()
    (again,) = list_raw_entries("coffer")

    assert again.entry_id == stored.entry_id
    assert again.entry.title == stored.entry.title
    assert again.entry.description == stored.entry.description
    assert again.entry.body == stored.entry.body


# --- Partition by repository plus global -------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="produce one partition per repository and one global"
)
async def test_two_repositories_and_a_preference_make_exactly_three_partitions(
    tmp_path: pathlib.Path,
) -> None:
    api = init_repository(tmp_path / "home" / "dev" / "api")
    web = init_repository(tmp_path / "home" / "dev" / "web")
    claude_dir = claude_code_config(
        tmp_path / "claude",
        api,
        {
            "api-fact.md": _cc_file("api-fact", "about the api", "project", "API body"),
            "likes-short-replies.md": _cc_file(
                "likes-short-replies", "the user prefers short replies", "user", "Be brief."
            ),
        },
    )
    claude_code_config(
        claude_dir, web, {"web-fact.md": _cc_file("web-fact", "about the web", "project", "Web")}
    )
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", str(claude_dir))

    await _service(resources).aggregate()

    assert store.list_partitions() == ("api", "global", "web")
    rows = await resources.list(kind=KIND_MEMORY)
    assert sorted(r.name for r in rows) == ["api", "global", "web"]
    assert len(rows) == 3  # each partition is exactly one `memory` Resource
    assert {e.entry.title for e in list_raw_entries("global")} == {"likes-short-replies"}


# --- Create partitions only by aggregation -----------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="compose context and recall without creating a partition"
)
async def test_reading_from_inside_a_repository_brings_no_partition_into_existence(
    tmp_path: pathlib.Path,
) -> None:
    repository = init_repository(tmp_path / "home" / "dev" / "coffer")
    cwd = repository / "src"
    cwd.mkdir()
    resources = FakeResources()
    service = _service(resources)
    root = paths.memory_root()
    assert not root.exists() or not any(root.iterdir())

    composed = await compose_context(service, cwd=str(cwd))
    recalled = await RecallService(memory=service).recall("coffer")

    assert composed.text == ""
    assert recalled.notes == ()
    assert store.list_partitions() == ()
    assert not (root / "coffer").exists()
    assert await resources.list(kind=KIND_MEMORY) == []


# --- Reintroduce no retired mechanism ----------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="register exactly the two readers")
async def test_the_registry_holds_two_readers_and_a_full_run_writes_only_the_four_parts(
    tmp_path: pathlib.Path,
) -> None:
    assert set(DEFAULT_READERS) == {"claude_code", "codex"}
    assert isinstance(DEFAULT_READERS["claude_code"], ClaudeCodeMemoryReader)
    assert isinstance(DEFAULT_READERS["codex"], CodexMemoryReader)

    repository = init_repository(tmp_path / "home" / "dev" / "coffer")
    claude_dir = claude_code_config(
        tmp_path / "claude",
        repository,
        {
            "lockfile.md": _cc_file("lockfile", "locked with uv", "project", "uv sync"),
            "brief.md": _cc_file("brief", "be brief", "user", "Short replies."),
        },
    )
    codex_dir = codex_config(
        tmp_path / "codex",
        f"# Task Group: daemon restart\n\napplies_to: cwd={repository}\n\n"
        "## Reusable knowledge\n\n- restart with coffer daemon stop/start\n",
        "v1\n\n## User preferences\n\n- ask before merging\n",
    )
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", str(claude_dir))
    resources.add_agent("codex", "codex", str(codex_dir))
    service = MemoryService(
        resources=resources,  # type: ignore[arg-type]
        audit=FakeAudit(),  # type: ignore[arg-type]
        agent_source_resolver=agent_source_resolver,
    )  # the default registry, not a substitute

    result = await service.aggregate()
    assert result.failures == ()
    assert {e.agent for e in _all_raw()} == {"claude-code", "codex"}
    for row in await resources.list(kind=KIND_MEMORY):
        await service.distil(row.uid)

    partitions = store.list_partitions()
    assert partitions == ("coffer", "global")
    allowed = {"MEMORY.md", "notes", "RETIRED.md", ".raw"}
    for partition in partitions:
        children = {p.name for p in paths.partition_dir(partition).iterdir()}
        assert children <= allowed, children
        assert {"MEMORY.md", "notes", ".raw"} <= children
    root = paths.memory_root()
    assert not any("journal" in p.name.lower() for p in root.rglob("*"))
