"""``MemoryService.aggregate`` and the pure merge/slug helpers it composes.

Fakes stand in for ``ResourceService``/``AuditService`` (same shape as
``tests/unit/knowledge/test_grep_and_scope.py``'s) and for the two readers —
per the task's own rule, a unit test fakes the readers rather than touching a
developer's real ``~/.claude``/``~/.codex``. The store and its paths are the
real filesystem module, writing under ``tmp_path`` — ``COFFER_MEMORY_ROOT`` is
pinned there by the suite-wide autouse fixture (``backend/tests/conftest.py``),
so this is still unit-tier: no subprocess, no real database, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from coffer.application.memory.aggregate import (
    AgentSource,
    SourceFailure,
    assign_slugs,
    merge_duplicates,
)
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.domain.errors import ResourceNotFound
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.fact import TYPE_FEEDBACK, TYPE_PROJECT, TYPE_USER, Fact, Origin
from coffer.domain.memory.reader import RawFact, SourceFile
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.scope import Scope
from coffer.infrastructure.memory import store

# --------------------------------------------------------------------------- #
# Fakes                                                                       #
# --------------------------------------------------------------------------- #


class _FakeResources:
    """Just enough ``ResourceService`` for aggregation's own needs."""

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
        self,
        *,
        kind: str,
        name: str,
        config: dict,
        actor: str,
        description: str | None = None,
        allow_lifecycle_kind: bool = False,
    ) -> Resource:
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
        await self.get(ref)  # raises if absent, like the real service
        del self._rows[(ref.kind, ref.name)]
        # In production, ResourceService.delete calls the kind's on_delete
        # hook (make_memory_kind's, which removes the directory) BEFORE the
        # row goes; this fake stands in for that one line of wiring so these
        # tests do not need the full Kind/ResourceService machinery.
        if ref.kind == KIND_MEMORY:
            store.delete_partition(ref.name)


class _FakeAudit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def record(self, event_type: str, *, ref=None, actor: str = "system", details=None):
        self.events.append((event_type, details or {}))


@dataclass
class _FakeReader:
    """A ``MemoryReader`` whose sources/content a test controls directly."""

    agent_type: str
    _sources: dict[str, list[SourceFile]] = field(default_factory=dict)
    _content: dict[str, object] = field(default_factory=dict)

    def set_sources(self, config_dir: str, sources: list[SourceFile]) -> None:
        self._sources[config_dir] = sources

    def set_content(self, path: str, result: object) -> None:
        """``result`` is a tuple of ``RawFact`` or an ``UnreadableMemory``."""
        self._content[path] = result

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        return tuple(self._sources.get(config_dir, []))

    def read(self, source: SourceFile) -> tuple[RawFact, ...]:
        result = self._content.get(source.path, ())
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]


def _agent_resource(
    name: str, agent_type: str, config_dir: str, *, enabled: bool = True
) -> Resource:
    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        kind="agent",
        name=name,
        description=None,
        config={"type": agent_type, "config_dir": config_dir},
        enabled=enabled,
        created_at=now,
        updated_at=now,
        scope=None,
    )


def _resolver(resource: Resource) -> AgentSource:
    return AgentSource(
        agent=resource.name,
        agent_type=resource.config["type"],
        config_dir=resource.config["config_dir"],
    )


def _service(resources: _FakeResources, readers: dict) -> MemoryService:
    return MemoryService(
        resources=resources,
        audit=_FakeAudit(),
        agent_source_resolver=_resolver,
        readers=readers,
    )


def _raw(
    title: str,
    body: str,
    *,
    type: str = TYPE_PROJECT,
    project_root: str = "",
    anchor: str = "",
) -> RawFact:
    return RawFact(
        title=title,
        description=body,
        type=type,
        body=body,
        anchor=anchor or title,
        project_root=project_root,
    )


# --------------------------------------------------------------------------- #
# Pure helpers                                                                #
# --------------------------------------------------------------------------- #


def _fact(
    title: str,
    body: str,
    *,
    partition: str = "coffer",
    type: str = TYPE_PROJECT,
    agent="a",
    path="p",
    anchor="",
) -> Fact:
    return Fact(
        slug="",
        title=title,
        description=body,
        type=type,
        body=body,
        partition=partition,
        origins=(Origin(agent=agent, native_path=path, anchor=anchor or title),),
    )


def test_merge_duplicates_merges_identical_body_across_agents() -> None:
    a = _fact("Worktree rule", "Always use a worktree.", agent="claude-code", path="/a")
    b = _fact("Different title", "Always use a worktree.", agent="codex", path="/b")
    merged = merge_duplicates([a, b])
    assert len(merged) == 1
    assert {o.agent for o in merged[0].origins} == {"claude-code", "codex"}


def test_merge_duplicates_merges_identical_type_partition_title() -> None:
    a = _fact("Same title", "body one", agent="claude-code", path="/a")
    b = _fact("same title", "body two, different", agent="codex", path="/b")
    merged = merge_duplicates([a, b])
    assert len(merged) == 1
    assert {o.agent for o in merged[0].origins} == {"claude-code", "codex"}


def test_merge_duplicates_leaves_unrelated_facts_apart() -> None:
    a = _fact("Fact A", "totally different body", agent="claude-code", path="/a")
    b = _fact("Fact B", "another distinct body", agent="codex", path="/b")
    merged = merge_duplicates([a, b])
    assert len(merged) == 2


def test_assign_slugs_preserves_an_existing_slug() -> None:
    fact = _fact("Some title", "some body")
    fact = Fact(**{**fact.__dict__, "slug": "kept-slug"})
    (out,) = assign_slugs([fact])
    assert out.slug == "kept-slug"


def test_assign_slugs_resolves_a_collision_with_a_numeric_suffix() -> None:
    a = _fact("Same Title", "body a", agent="x", path="/a")
    b = _fact("Same Title", "body b", agent="y", path="/b")
    out = assign_slugs([a, b])
    slugs = sorted(f.slug for f in out)
    assert slugs == ["same-title", "same-title-2"]


# --------------------------------------------------------------------------- #
# MemoryService.aggregate                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a project partition is named from its root, never from an opaque id"
)
async def test_a_fact_lands_in_its_projects_partition() -> None:
    resources = _FakeResources()
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(
        source.path,
        (
            _raw(
                "Use a worktree",
                "Always develop in a git worktree.",
                project_root="/home/dev/coffer",
            ),
        ),
    )
    await resources.register(
        kind="agent", name="claude-code", config={}, actor="t", allow_lifecycle_kind=True
    )
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")

    result = await _service(resources, {"claude_code": reader}).aggregate()

    assert result.partitions == ("coffer",)
    facts = store.list_facts("coffer")
    assert len(facts) == 1
    assert facts[0].title == "Use a worktree"


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a preference lands in global regardless of which project it came from",
)
async def test_a_personal_fact_lands_in_global_even_from_a_project() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/pref.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(
        source.path,
        (
            _raw(
                "Reply in Chinese",
                "The user prefers Chinese replies.",
                type=TYPE_USER,
                project_root="/home/dev/coffer",
            ),
        ),
    )

    result = await _service(resources, {"claude_code": reader}).aggregate()

    assert result.partitions == ("global",)
    assert len(store.list_facts("global")) == 1


@pytest.mark.asyncio
async def test_a_fact_whose_root_is_home_lands_in_global() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "codex")] = _agent_resource("codex", "codex", "/codex-home")
    reader = _FakeReader(agent_type="codex")
    source = SourceFile(path="/codex-home/memories/memory_summary.md", digest="d1")
    reader.set_sources("/codex-home", [source])
    reader.set_content(
        source.path,
        (_raw("User profile", "Works on Coffer.", type=TYPE_FEEDBACK, project_root="/home/dev"),),
    )

    result = await _service(resources, {"codex": reader}).aggregate(actor="t")
    assert result.partitions == ("global",)


@pytest.mark.acceptance(
    spec="memory",
    scenario="an unchanged source file is skipped on the next sync",
)
@pytest.mark.asyncio
async def test_unchanged_source_is_not_reparsed_but_survives() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="same-digest")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("Title", "Body.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})

    first = await service.aggregate()
    assert first.sources_read == 1
    assert first.sources_skipped == 0

    # A second read must not be consulted at all: swap the content for
    # something that would raise if `reader.read` were called again.
    reader.set_content(source.path, UnreadableMemory(source.path, "must not be re-parsed"))

    second = await service.aggregate()
    assert second.sources_read == 0
    assert second.sources_skipped == 1
    assert second.failures == ()
    assert len(store.list_facts("coffer")) == 1


@pytest.mark.asyncio
async def test_a_changed_sources_facts_are_replaced() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    path = "/cc/projects/coffer/memory/f.md"
    source_v1 = SourceFile(path=path, digest="v1")
    reader.set_sources("/cc", [source_v1])
    reader.set_content(path, (_raw("Old title", "Old body.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()
    assert store.list_facts("coffer")[0].title == "Old title"

    source_v2 = SourceFile(path=path, digest="v2")
    reader.set_sources("/cc", [source_v2])
    reader.set_content(path, (_raw("New title", "New body.", project_root="/home/dev/coffer"),))
    result = await service.aggregate()

    assert result.sources_read == 1
    facts = store.list_facts("coffer")
    assert len(facts) == 1
    assert facts[0].title == "New title"


@pytest.mark.asyncio
async def test_a_vanished_sources_facts_are_dropped() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    keep = SourceFile(path="/cc/projects/coffer/memory/keep.md", digest="k1")
    gone = SourceFile(path="/cc/projects/coffer/memory/gone.md", digest="g1")
    reader.set_sources("/cc", [keep, gone])
    reader.set_content(keep.path, (_raw("Keep", "Keep body.", project_root="/home/dev/coffer"),))
    reader.set_content(gone.path, (_raw("Gone", "Gone body.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()
    assert {f.title for f in store.list_facts("coffer")} == {"Keep", "Gone"}

    reader.set_sources("/cc", [keep])  # "gone" no longer reported by sources()
    await service.aggregate()

    assert {f.title for f in store.list_facts("coffer")} == {"Keep"}


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an agent whose native memory shape is unreadable degrades loudly"
)
async def test_unreadable_memory_in_one_agent_leaves_the_other_intact() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    resources._rows[("agent", "codex")] = _agent_resource("codex", "codex", "/codex")
    cc_reader = _FakeReader(agent_type="claude_code")
    codex_reader = _FakeReader(agent_type="codex")

    broken = SourceFile(path="/cc/projects/coffer/memory/broken.md", digest="b1")
    cc_reader.set_sources("/cc", [broken])
    cc_reader.set_content(broken.path, UnreadableMemory(broken.path, "bad frontmatter"))

    good = SourceFile(path="/codex/memories/MEMORY.md", digest="g1")
    codex_reader.set_sources("/codex", [good])
    codex_reader.set_content(
        good.path, (_raw("Codex fact", "Codex body.", project_root="/home/dev/coffer"),)
    )

    service = _service(resources, {"claude_code": cc_reader, "codex": codex_reader})
    result = await service.aggregate()

    assert len(result.failures) == 1
    assert result.failures[0] == SourceFailure(
        agent="claude-code", path=broken.path, reason="bad frontmatter"
    )
    assert {f.title for f in store.list_facts("coffer")} == {"Codex fact"}


@pytest.mark.asyncio
async def test_previously_aggregated_facts_survive_a_later_failure() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    path = "/cc/projects/coffer/memory/f.md"
    reader.set_sources("/cc", [SourceFile(path=path, digest="v1")])
    reader.set_content(path, (_raw("Title", "Body.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()
    assert len(store.list_facts("coffer")) == 1

    # The file changed (new digest) but is now unparsable.
    reader.set_sources("/cc", [SourceFile(path=path, digest="v2-broken")])
    reader.set_content(path, UnreadableMemory(path, "corrupted"))
    result = await service.aggregate()

    assert len(result.failures) == 1
    assert len(store.list_facts("coffer")) == 1  # left standing, not deleted


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="the same fact learned by two agents is reported as one with two origins",
)
async def test_two_agents_contributing_an_identical_body_merge_to_one_fact() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    resources._rows[("agent", "codex")] = _agent_resource("codex", "codex", "/codex")
    cc_reader = _FakeReader(agent_type="claude_code")
    codex_reader = _FakeReader(agent_type="codex")

    cc_source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    cc_reader.set_sources("/cc", [cc_source])
    cc_reader.set_content(
        cc_source.path,
        (_raw("CC title", "Always develop in a worktree.", project_root="/home/dev/coffer"),),
    )

    codex_source = SourceFile(path="/codex/memories/MEMORY.md", digest="d2")
    codex_reader.set_sources("/codex", [codex_source])
    codex_reader.set_content(
        codex_source.path,
        (_raw("Codex title", "Always develop in a worktree.", project_root="/home/dev/coffer"),),
    )

    service = _service(resources, {"claude_code": cc_reader, "codex": codex_reader})
    result = await service.aggregate()

    facts = store.list_facts("coffer")
    assert len(facts) == 1
    assert result.facts_written == 1
    assert {o.agent for o in facts[0].origins} == {"claude-code", "codex"}


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a partition is registered as a resource scoped to the agents it came from",
)
async def test_a_new_partition_is_scoped_to_its_source_agents() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("T", "B.", project_root="/home/dev/coffer"),))

    await _service(resources, {"claude_code": reader}).aggregate()

    row = await resources.get(ResourceRef(KIND_MEMORY, "coffer"))
    # The partition is scoped to the agent it was aggregated from.
    assert row.scope == Scope(agents=["claude-code"])
    assert row.config["project_root"] == "/home/dev/coffer"


@pytest.mark.asyncio
async def test_an_existing_partitions_scope_is_never_overwritten() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("T", "B.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()

    # The developer narrows the scope by hand.
    await resources.update_scope(ResourceRef(KIND_MEMORY, "coffer"), Scope(agents=[]), actor="dev")

    # A later pass with a changed source must not touch the scope again.
    reader.set_sources("/cc", [SourceFile(path=source.path, digest="d2")])
    reader.set_content(source.path, (_raw("T2", "B2.", project_root="/home/dev/coffer"),))
    await service.aggregate()

    row = await resources.get(ResourceRef(KIND_MEMORY, "coffer"))
    assert row.scope == Scope(agents=[])


@pytest.mark.asyncio
async def test_an_emptied_partition_and_its_resource_are_removed() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("T", "B.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()
    assert store.list_partitions() == ("coffer",)

    reader.set_sources("/cc", [])  # the source itself vanished
    await service.aggregate()

    assert store.list_partitions() == ()
    with pytest.raises(ResourceNotFound):
        await resources.get(ResourceRef(KIND_MEMORY, "coffer"))


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="deleting the memory tree and re-syncing reproduces the facts"
)
async def test_deleting_the_tree_and_resyncing_reproduces_the_facts() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("T", "B.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()
    before = store.list_facts("coffer")

    # Delete the partition directories but — deliberately — not the
    # source-digest cache, to prove the digest match alone never suppresses a
    # reparse: a rebuild must work even when only part of the derived tree
    # was cleared by hand (FR-023).
    for name in store.list_partitions():
        store.delete_partition(name)

    await service.aggregate()
    after = store.list_facts("coffer")
    assert [f.title for f in after] == [f.title for f in before]


@pytest.mark.asyncio
async def test_a_second_pass_with_nothing_changed_writes_nothing() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("T", "B.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()

    result = await service.aggregate()

    assert result.facts_written == 0
    assert result.sources_skipped == 1


@pytest.mark.asyncio
async def test_an_agent_with_no_reader_contributes_nothing() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "mystery")] = _agent_resource("mystery", "mystery_type", "/m")
    service = _service(resources, {"claude_code": _FakeReader(agent_type="claude_code")})
    result = await service.aggregate()
    assert result.partitions == ()
    assert result.facts_written == 0


@pytest.mark.asyncio
async def test_a_disabled_agent_is_not_read() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource(
        "claude-code", "claude_code", "/cc", enabled=False
    )
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("T", "B.", project_root="/home/dev/coffer"),))
    result = await _service(resources, {"claude_code": reader}).aggregate()
    assert result.partitions == ()


@pytest.mark.asyncio
async def test_visible_partitions_enforces_scope() -> None:
    resources = _FakeResources()
    resources._rows[("agent", "claude-code")] = _agent_resource("claude-code", "claude_code", "/cc")
    reader = _FakeReader(agent_type="claude_code")
    source = SourceFile(path="/cc/projects/coffer/memory/f.md", digest="d1")
    reader.set_sources("/cc", [source])
    reader.set_content(source.path, (_raw("T", "B.", project_root="/home/dev/coffer"),))
    service = _service(resources, {"claude_code": reader})
    await service.aggregate()

    assert await service.visible_partitions("claude-code") == ["coffer"]
    assert await service.visible_partitions("codex") == []
    assert await service.list_facts("coffer", agent="codex") == ()
    assert len(await service.list_facts("coffer", agent="claude-code")) == 1
