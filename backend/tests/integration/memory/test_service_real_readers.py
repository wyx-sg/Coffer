"""``MemoryService.aggregate`` over the two REAL readers (spec memory User
Story 1: what one agent learns, the others know).

Integration rather than unit because this exercises the real
``ClaudeCodeMemoryReader``/``CodexMemoryReader`` parsing a realistic fixture
tree, end to end through ``MemoryService`` and the real file-backed store —
the readers themselves are unit-tested in ``tests/unit/memory``, and
``MemoryService``'s own algorithm (skip/fail/merge/scope) against fakes in
``tests/unit/memory/test_aggregate.py``. This is the seam between them: real
parsers, real partition files, one pass.

``ResourceService``/``AuditService`` stay fake (same shape as
``tests/unit/knowledge/test_grep_and_scope.py``'s) — nothing here needs a real
database, and the fixture agent directories live entirely under ``tmp_path``.
"""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

import pytest

from coffer.application.memory.aggregate import AgentSource
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.application.scope_evaluator import ScopeEvaluator
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource, ResourceRef
from coffer.infrastructure.memory.readers import ClaudeCodeMemoryReader, CodexMemoryReader

# --------------------------------------------------------------------------- #
# Fake ResourceService/AuditService — no real database needed (see module
# docstring); mirrors tests/unit/knowledge/test_grep_and_scope.py.
# --------------------------------------------------------------------------- #


class _FakeResources:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], Resource] = {}
        self._next_id = 1

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        return [
            r
            for r in self._rows.values()
            if (kind is None or r.kind == kind) and (enabled is None or r.enabled == enabled)
        ]

    async def get(self, ref: ResourceRef) -> Resource:
        row = self._rows.get((ref.kind, ref.name))
        if row is None:
            raise ResourceNotFound(ref.kind, ref.name)
        return row

    async def register(
        self, *, kind, name, config, actor, description=None, allow_lifecycle_kind=False
    ):
        now = datetime.now(tz=UTC)
        row = Resource(
            id=self._next_id,
            kind=kind,
            name=name,
            description=description,
            config=config,
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self._next_id += 1
        self._rows[(kind, name)] = row
        return row

    async def update_scope(self, ref: ResourceRef, scope, *, actor: str) -> Resource:
        row = await self.get(ref)
        row.scope = scope
        return row

    async def delete(self, ref: ResourceRef, actor: str) -> None:
        from coffer.infrastructure.memory import store

        await self.get(ref)
        del self._rows[(ref.kind, ref.name)]
        if ref.kind == KIND_MEMORY:
            store.delete_partition(ref.name)

    def add_agent(self, name: str, agent_type: str, config_dir: str) -> None:
        now = datetime.now(tz=UTC)
        self._rows[("agent", name)] = Resource(
            id=self._next_id,
            kind="agent",
            name=name,
            description=None,
            config={"type": agent_type, "config_dir": config_dir},
            enabled=True,
            created_at=now,
            updated_at=now,
            scope=None,
        )
        self._next_id += 1


class _FakeAudit:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def record(self, event_type, *, ref=None, actor="system", details=None):
        self.events.append(event_type)


def _resolver(resource: Resource) -> AgentSource:
    return AgentSource(
        agent=resource.name,
        agent_type=resource.config["type"],
        config_dir=resource.config["config_dir"],
    )


# --------------------------------------------------------------------------- #
# Fixture tree: a real Claude Code project directory + a real Codex config.  #
# --------------------------------------------------------------------------- #


def _encode(name: str) -> str:
    return "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in name)


def _cc_slug(project_root: pathlib.Path) -> str:
    encode = _encode
    parts = [p for p in project_root.parts if p != "/"]
    return "-" + "-".join(encode(p) for p in parts)


_CC_PREFERENCE_FACT = """---
name: worktree-development
description: Always develop in a git worktree
metadata:
  type: feedback
---

Multiple parallel sessions share the repo — always work in a worktree.
"""

_CC_PROJECT_FACT = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  type: project
---

Run `uv sync --frozen` in this project; a plain `pip install` drifts.
"""

_CODEX_MEMORY_MD = """# Task Group: coffer work

applies_to: cwd={project_root}

## Reusable knowledge

- the coffer daemon restarts with `coffer daemon stop/start`. [Task 1]
"""

_CODEX_SUMMARY_MD = """## User Profile

Works primarily on the Coffer project, prefers concise answers.
"""


@pytest.fixture
def fixture(tmp_path: pathlib.Path):
    project_root = tmp_path / "home" / "dev" / "coffer"
    project_root.mkdir(parents=True)

    cc_config_dir = tmp_path / "claude"
    cc_memory_dir = cc_config_dir / "projects" / _cc_slug(project_root) / "memory"
    cc_memory_dir.mkdir(parents=True)
    cc_pref_path = cc_memory_dir / "worktree-development.md"
    cc_pref_path.write_text(_CC_PREFERENCE_FACT, encoding="utf-8")
    cc_project_path = cc_memory_dir / "python-lockfile.md"
    cc_project_path.write_text(_CC_PROJECT_FACT, encoding="utf-8")
    cc_original_bytes = {
        cc_pref_path: cc_pref_path.read_bytes(),
        cc_project_path: cc_project_path.read_bytes(),
    }

    codex_config_dir = tmp_path / "codex"
    memories_dir = codex_config_dir / "memories"
    memories_dir.mkdir(parents=True)
    memory_md_path = memories_dir / "MEMORY.md"
    memory_md_path.write_text(_CODEX_MEMORY_MD.format(project_root=project_root), encoding="utf-8")
    summary_path = memories_dir / "memory_summary.md"
    summary_path.write_text(_CODEX_SUMMARY_MD, encoding="utf-8")
    codex_original_bytes = {
        memory_md_path: memory_md_path.read_bytes(),
        summary_path: summary_path.read_bytes(),
    }

    resources = _FakeResources()
    resources.add_agent("claude-code", "claude_code", str(cc_config_dir))
    resources.add_agent("codex", "codex", str(codex_config_dir))

    service = MemoryService(
        resources=resources,
        audit=_FakeAudit(),
        agent_source_resolver=_resolver,
        scope_evaluator=ScopeEvaluator(machine_id="test-machine"),
        readers={"claude_code": ClaudeCodeMemoryReader(), "codex": CodexMemoryReader()},
    )
    return {
        "service": service,
        "resources": resources,
        "project_root": project_root,
        "cc_original_bytes": cc_original_bytes,
        "codex_original_bytes": codex_original_bytes,
    }


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a fact keeps the agent, path and time it came from"
)
async def test_both_agents_native_memory_land_in_the_same_project_partition(fixture) -> None:
    from coffer.infrastructure.memory import store

    result = await fixture["service"].aggregate()

    assert "coffer" in result.partitions
    facts = store.list_facts("coffer")
    titles = {f.title for f in facts}
    assert "worktree-development" not in titles  # it is a `feedback` type — personal, → global
    assert "python-lockfile" in titles
    assert any("coffer daemon restarts" in f.body for f in facts)
    origins_agents = {o.agent for f in facts for o in f.origins}
    assert origins_agents == {"claude-code", "codex"}


@pytest.mark.asyncio
async def test_feedback_and_profile_facts_land_in_global(fixture) -> None:
    from coffer.infrastructure.memory import store

    await fixture["service"].aggregate()

    global_titles = {f.title for f in store.list_facts("global")}
    assert "worktree-development" in global_titles
    assert "User Profile" in global_titles


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="aggregation never modifies an agent's native memory files"
)
async def test_native_memory_files_are_byte_identical_after_aggregation(fixture) -> None:
    await fixture["service"].aggregate()

    for path, original in fixture["cc_original_bytes"].items():
        assert path.read_bytes() == original
    for path, original in fixture["codex_original_bytes"].items():
        assert path.read_bytes() == original


@pytest.mark.asyncio
async def test_the_project_partition_is_scoped_to_both_agents(fixture) -> None:
    await fixture["service"].aggregate()

    row = await fixture["resources"].get(ResourceRef(KIND_MEMORY, "coffer"))
    # The agent axis names both sources; the machine axis stays unrestricted,
    # because a partition belongs wherever those agents are (spec vault-sync).
    assert row.scope is not None
    assert set(row.scope.agents or []) == {"claude-code", "codex"}
    assert row.scope.machines is None
    assert row.config["project_root"] == str(fixture["project_root"])
