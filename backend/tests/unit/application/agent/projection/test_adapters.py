"""Unit tests for the agent-side memory projection adapters (spec 007).

Covers the 007 projection acceptance scenarios against the real
``ProjectionFsAdapter`` under a temp HOME:

- slug computation (Claude ``~/.claude/projects/<slug>``),
- project memory projects into Claude as a symlink,
- existing native memory files are merged, never overwritten,
- global memory renders a managed block into Codex AGENTS.md,
- re-rendering a managed block is idempotent,
- disable-native-memory (Codex ``memories``),
- render output.
"""

from __future__ import annotations

import pytest

from coffer.application.agent.projection import (
    MANAGED_BLOCK_END,
    MANAGED_BLOCK_START,
    CanonicalMemory,
    ClaudeCodeMemoryAdapter,
    CodexMemoryAdapter,
    HermesMemoryAdapter,
    MemoryLayer,
    OpenClawMemoryAdapter,
    OpenCodeMemoryAdapter,
    ProjectionEngine,
    ProjectionMode,
    claude_project_slug,
)
from coffer.application.agent.projection.engine import default_adapters
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.projection_fs import ProjectionFsAdapter


@pytest.fixture
def fs() -> ProjectionFsAdapter:
    return ProjectionFsAdapter()


def _canonical(tmp_path, layer: MemoryLayer, *, name: str = "store") -> CanonicalMemory:
    store_dir = tmp_path / "memory" / name
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "MEMORY.md").write_text("# Memory\n", encoding="utf-8")
    rendered = "# Memory\n\n- [a fact](fact.md) — a description\n"
    return CanonicalMemory(store_dir=store_dir, rendered=rendered, layer=layer)


# --------------------------------------------------------------------------- #
# slug                                                                         #
# --------------------------------------------------------------------------- #


def test_claude_project_slug_matches_claude_convention():
    assert claude_project_slug("/Users/xing/Coffer") == "-Users-xing-Coffer"
    assert claude_project_slug("/a/b.c/d") == "-a-b-c-d"


def test_claude_project_slug_does_not_collapse_consecutive_separators():
    # Claude replaces EACH non-alnum char with a dash (no run-collapsing), so a
    # hidden dir yields a double dash. A ``+`` quantifier would wrongly produce
    # ``-Users-xing-claude`` and point the symlink at the wrong dir (finding #2).
    assert claude_project_slug("/Users/xing/.claude") == "-Users-xing--claude"
    assert claude_project_slug("/x/.hidden") == "-x--hidden"


# --------------------------------------------------------------------------- #
# Claude Code — SYMLINK                                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.acceptance(
    spec="007-memory", scenario="project memory projects into Claude as a symlink"
)
def test_project_memory_projects_into_claude_as_symlink(tmp_path, fs):
    claude_dir = tmp_path / ".claude"
    adapter = ClaudeCodeMemoryAdapter(fs, config_dir=claude_dir)
    project_root = "/work/my-repo"
    memory = _canonical(tmp_path, MemoryLayer.PROJECT, name="proj")

    result = adapter.establish(memory=memory, project_root=project_root, agent_ref="claude")

    slug = claude_project_slug(project_root)
    link = claude_dir / "projects" / slug / "memory"
    assert link.is_symlink()
    assert link.resolve() == memory.store_dir.resolve()
    assert result.projection_mode is ProjectionMode.SYMLINK
    # Claude auto-memory stays ON (the symlink IS the memory dir).
    assert result.native_memory_disabled is False
    # Editing through the symlink writes into the canonical store.
    (link / "edited.md").write_text("edited via symlink", encoding="utf-8")
    assert (memory.store_dir / "edited.md").read_text(encoding="utf-8") == "edited via symlink"


def test_symlink_establish_is_idempotent(tmp_path, fs):
    claude_dir = tmp_path / ".claude"
    adapter = ClaudeCodeMemoryAdapter(fs, config_dir=claude_dir)
    memory = _canonical(tmp_path, MemoryLayer.PROJECT, name="proj")
    r1 = adapter.establish(memory=memory, project_root="/p", agent_ref="c")
    r2 = adapter.establish(memory=memory, project_root="/p", agent_ref="c")
    assert r1.target_path == r2.target_path
    assert r2.merged_existing is False  # nothing to merge on the second run


@pytest.mark.acceptance(
    spec="007-memory", scenario="existing native memory files are merged, never overwritten"
)
def test_existing_native_files_merged_never_overwritten(tmp_path, fs):
    claude_dir = tmp_path / ".claude"
    adapter = ClaudeCodeMemoryAdapter(fs, config_dir=claude_dir)
    memory = _canonical(tmp_path, MemoryLayer.PROJECT, name="proj")
    # Canonical store already holds one fact (the one we must NOT clobber).
    (memory.store_dir / "keep.md").write_text("canonical wins", encoding="utf-8")

    # Claude's native dir pre-exists with a real file + a colliding name.
    slug = claude_project_slug("/p")
    native = claude_dir / "projects" / slug / "memory"
    native.mkdir(parents=True, exist_ok=True)
    (native / "native-only.md").write_text("native only", encoding="utf-8")
    (native / "keep.md").write_text("native loser", encoding="utf-8")

    result = adapter.establish(memory=memory, project_root="/p", agent_ref="c")

    assert native.is_symlink()
    assert result.merged_existing is True
    # The native-only file migrated into the canonical store.
    assert (memory.store_dir / "native-only.md").read_text(encoding="utf-8") == "native only"
    # The colliding name kept the canonical copy (never silently overwritten).
    assert (memory.store_dir / "keep.md").read_text(encoding="utf-8") == "canonical wins"


def test_native_file_name_collision_preserves_both(tmp_path, fs):
    # A real fact-file name collision must keep the canonical copy AND preserve
    # the incoming native file under a deduped name — the user's file is never
    # lost (a later rmtree of the native dir must not delete un-migrated data).
    # MEMORY.md is the one exception (derived index, safe to discard).
    claude_dir = tmp_path / ".claude"
    adapter = ClaudeCodeMemoryAdapter(fs, config_dir=claude_dir)
    memory = _canonical(tmp_path, MemoryLayer.PROJECT, name="proj")
    (memory.store_dir / "fact.md").write_text("canonical body", encoding="utf-8")

    slug = claude_project_slug("/p")
    native = claude_dir / "projects" / slug / "memory"
    native.mkdir(parents=True, exist_ok=True)
    (native / "fact.md").write_text("native body — must NOT be lost", encoding="utf-8")
    (native / "MEMORY.md").write_text("# stale native index\n", encoding="utf-8")

    result = adapter.establish(memory=memory, project_root="/p", agent_ref="c")

    assert native.is_symlink()
    assert result.merged_existing is True
    # Canonical copy kept verbatim.
    assert (memory.store_dir / "fact.md").read_text(encoding="utf-8") == "canonical body"
    # The colliding native file was preserved under a deduped name (not dropped).
    preserved = memory.store_dir / "fact.imported-1.md"
    assert preserved.read_text(encoding="utf-8") == "native body — must NOT be lost"
    # The derived index collision is discarded (no MEMORY.imported-1.md spam).
    assert not (memory.store_dir / "MEMORY.imported-1.md").exists()


def test_claude_global_renders_managed_block_into_claude_md(tmp_path, fs):
    claude_dir = tmp_path / ".claude"
    adapter = ClaudeCodeMemoryAdapter(fs, config_dir=claude_dir)
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="global")
    result = adapter.establish(memory=memory, project_root=None, agent_ref="c")
    target = claude_dir / "CLAUDE.md"
    assert target.exists()
    text = target.read_text(encoding="utf-8")
    assert MANAGED_BLOCK_START in text and MANAGED_BLOCK_END in text
    assert "a fact" in text
    assert result.target_path == str(target)


def test_claude_remove_unlinks_symlink_only(tmp_path, fs):
    claude_dir = tmp_path / ".claude"
    adapter = ClaudeCodeMemoryAdapter(fs, config_dir=claude_dir)
    memory = _canonical(tmp_path, MemoryLayer.PROJECT, name="proj")
    adapter.establish(memory=memory, project_root="/p", agent_ref="c")
    link = claude_dir / "projects" / claude_project_slug("/p") / "memory"
    assert link.is_symlink()
    adapter.remove(project_root="/p", layer=MemoryLayer.PROJECT)
    assert not link.exists()
    # Canonical store untouched.
    assert memory.store_dir.exists()


# --------------------------------------------------------------------------- #
# Codex — RENDER                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.acceptance(
    spec="007-memory", scenario="global memory renders a managed block into Codex AGENTS.md"
)
def test_global_memory_renders_managed_block_into_codex_agents_md(tmp_path, fs):
    codex_dir = tmp_path / ".codex"
    adapter = CodexMemoryAdapter(fs, config_dir=codex_dir)
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="global")
    # Pre-existing content outside the markers must be preserved.
    agents = codex_dir / "AGENTS.md"
    agents.parent.mkdir(parents=True, exist_ok=True)
    agents.write_text("# My instructions\n\nKeep this.\n", encoding="utf-8")

    result = adapter.establish(memory=memory, project_root=None, agent_ref="codex")

    text = agents.read_text(encoding="utf-8")
    assert "Keep this." in text  # content outside markers untouched
    assert MANAGED_BLOCK_START in text
    assert MANAGED_BLOCK_END in text
    assert "a fact" in text
    # Codex native memory disabled so no second copy accumulates.
    assert result.native_memory_disabled is True
    config = (codex_dir / "config.toml").read_text(encoding="utf-8")
    assert "[memories]" in config
    assert "enabled = false" in config


@pytest.mark.acceptance(spec="007-memory", scenario="re-rendering a managed block is idempotent")
def test_rerendering_a_managed_block_is_idempotent(tmp_path, fs):
    codex_dir = tmp_path / ".codex"
    adapter = CodexMemoryAdapter(fs, config_dir=codex_dir)
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="global")
    adapter.establish(memory=memory, project_root=None, agent_ref="codex")
    first = (codex_dir / "AGENTS.md").read_text(encoding="utf-8")
    # Same facts → byte-identical render on the second run.
    adapter.establish(memory=memory, project_root=None, agent_ref="codex")
    second = (codex_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
    # And config.toml stays disabled (idempotent), not duplicated.
    config = (codex_dir / "config.toml").read_text(encoding="utf-8")
    assert config.count("[memories]") == 1


def test_codex_disable_native_memory_preserves_other_config(tmp_path, fs):
    codex_dir = tmp_path / ".codex"
    config_path = codex_dir / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text('model = "gpt-5"\n\n[memories]\nenabled = true\n', encoding="utf-8")
    adapter = CodexMemoryAdapter(fs, config_dir=codex_dir)
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="global")
    adapter.establish(memory=memory, project_root=None, agent_ref="codex")
    text = config_path.read_text(encoding="utf-8")
    assert 'model = "gpt-5"' in text
    assert "enabled = false" in text
    assert "enabled = true" not in text


def test_codex_disable_native_memory_preserves_enabled_prefixed_sibling(tmp_path, fs):
    # An exact-key match must rewrite only ``enabled``; a sibling key that merely
    # starts with ``enabled`` (e.g. ``enabled_extra``) is left untouched
    # (finding #8 — a ``startswith`` check would corrupt it).
    codex_dir = tmp_path / ".codex"
    config_path = codex_dir / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        '[memories]\nenabled = true\nenabled_extra = "keep-me"\n', encoding="utf-8"
    )
    adapter = CodexMemoryAdapter(fs, config_dir=codex_dir)
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="global")
    adapter.establish(memory=memory, project_root=None, agent_ref="codex")
    text = config_path.read_text(encoding="utf-8")
    assert "enabled = false" in text
    assert "enabled = true" not in text
    assert 'enabled_extra = "keep-me"' in text  # sibling key untouched


def test_codex_project_renders_into_project_agents_md(tmp_path, fs):
    codex_dir = tmp_path / ".codex"
    adapter = CodexMemoryAdapter(fs, config_dir=codex_dir)
    project_root = tmp_path / "repo"
    project_root.mkdir()
    memory = _canonical(tmp_path, MemoryLayer.PROJECT, name="proj")
    result = adapter.establish(memory=memory, project_root=str(project_root), agent_ref="codex")
    assert result.target_path == str(project_root / "AGENTS.md")
    assert (project_root / "AGENTS.md").exists()


def test_codex_remove_strips_managed_block_keeps_rest(tmp_path, fs):
    codex_dir = tmp_path / ".codex"
    adapter = CodexMemoryAdapter(fs, config_dir=codex_dir)
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="global")
    agents = codex_dir / "AGENTS.md"
    agents.parent.mkdir(parents=True, exist_ok=True)
    agents.write_text("# Keep me\n", encoding="utf-8")
    adapter.establish(memory=memory, project_root=None, agent_ref="codex")
    adapter.remove(project_root=None, layer=MemoryLayer.GLOBAL)
    text = agents.read_text(encoding="utf-8")
    assert "Keep me" in text
    assert MANAGED_BLOCK_START not in text
    assert MANAGED_BLOCK_END not in text


def test_render_returns_markdown_bytes(tmp_path, fs):
    adapter = CodexMemoryAdapter(fs, config_dir=tmp_path / ".codex")
    assert adapter.render("# Memory\n- x\n") == b"# Memory\n- x\n"


# --------------------------------------------------------------------------- #
# ProjectionEngine dispatch                                                    #
# --------------------------------------------------------------------------- #


def test_engine_dispatches_on_projection_mode(tmp_path, fs):
    engine = ProjectionEngine(fs)
    assert engine.projection_mode(AgentType.CLAUDE_CODE) is ProjectionMode.SYMLINK
    assert engine.projection_mode(AgentType.CODEX) is ProjectionMode.RENDER


def test_engine_establish_routes_to_codex_adapter(tmp_path, fs):
    engine = ProjectionEngine(fs)
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="global")
    # Point the codex adapter's config dir at tmp via a fresh registry.
    codex_dir = tmp_path / ".codex"
    engine = ProjectionEngine(
        fs,
        adapters={
            AgentType.CODEX: CodexMemoryAdapter(fs, config_dir=codex_dir),
            AgentType.CLAUDE_CODE: ClaudeCodeMemoryAdapter(fs, config_dir=tmp_path / ".claude"),
        },
    )
    result = engine.establish(
        agent_type=AgentType.CODEX, agent_ref="codex", memory=memory, project_root=None
    )
    assert result.projection_mode is ProjectionMode.RENDER
    assert (codex_dir / "AGENTS.md").exists()


# --------------------------------------------------------------------------- #
# OpenCode / OpenClaw / Hermes — RENDER                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.acceptance(
    spec="007-memory", scenario="memory renders a managed block into OpenCode AGENTS.md"
)
def test_opencode_renders_managed_block_into_agents_md(tmp_path, fs):
    config_dir = tmp_path / ".config" / "opencode"
    adapter = OpenCodeMemoryAdapter(fs, config_dir=config_dir)
    assert adapter.projection_mode is ProjectionMode.RENDER

    project_root = tmp_path / "repo"
    project_root.mkdir()
    # memory_location for both layers.
    assert adapter.memory_location(project_root=str(project_root), layer=MemoryLayer.PROJECT) == (
        project_root / "AGENTS.md"
    )
    assert adapter.memory_location(project_root=None, layer=MemoryLayer.GLOBAL) == (
        config_dir / "AGENTS.md"
    )

    # GLOBAL: managed block written, native memory NOT disabled.
    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="oc-global")
    result = adapter.establish(memory=memory, project_root=None, agent_ref="oc")
    target = config_dir / "AGENTS.md"
    text = target.read_text(encoding="utf-8")
    assert MANAGED_BLOCK_START in text and MANAGED_BLOCK_END in text
    assert "a fact" in text
    assert result.projection_mode is ProjectionMode.RENDER
    assert result.native_memory_disabled is False
    assert result.target_path == str(target)

    # remove strips the block.
    adapter.remove(project_root=None, layer=MemoryLayer.GLOBAL)
    after = target.read_text(encoding="utf-8")
    assert MANAGED_BLOCK_START not in after


def test_opencode_project_preserves_surrounding_content(tmp_path, fs):
    config_dir = tmp_path / ".config" / "opencode"
    adapter = OpenCodeMemoryAdapter(fs, config_dir=config_dir)
    project_root = tmp_path / "repo"
    project_root.mkdir()
    agents = project_root / "AGENTS.md"
    agents.write_text("# Project rules\n\nKeep me.\n", encoding="utf-8")
    memory = _canonical(tmp_path, MemoryLayer.PROJECT, name="oc-proj")
    adapter.establish(memory=memory, project_root=str(project_root), agent_ref="oc")
    text = agents.read_text(encoding="utf-8")
    assert "Keep me." in text
    assert MANAGED_BLOCK_START in text


@pytest.mark.acceptance(
    spec="007-memory", scenario="memory renders a managed block into OpenClaw MEMORY.md"
)
def test_openclaw_renders_managed_block_into_memory_md(tmp_path, fs):
    config_dir = tmp_path / ".openclaw"
    adapter = OpenClawMemoryAdapter(fs, config_dir=config_dir)
    assert adapter.projection_mode is ProjectionMode.RENDER

    project_root = tmp_path / "repo"
    project_root.mkdir()
    assert adapter.memory_location(project_root=str(project_root), layer=MemoryLayer.PROJECT) == (
        project_root / "MEMORY.md"
    )
    assert adapter.memory_location(project_root=None, layer=MemoryLayer.GLOBAL) == (
        config_dir / "MEMORY.md"
    )

    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="claw-global")
    result = adapter.establish(memory=memory, project_root=None, agent_ref="claw")
    target = config_dir / "MEMORY.md"
    text = target.read_text(encoding="utf-8")
    assert MANAGED_BLOCK_START in text and "a fact" in text
    assert result.native_memory_disabled is False

    adapter.remove(project_root=None, layer=MemoryLayer.GLOBAL)
    assert MANAGED_BLOCK_START not in target.read_text(encoding="utf-8")


@pytest.mark.acceptance(
    spec="007-memory", scenario="memory renders a managed block into a Hermes memories file"
)
def test_hermes_renders_one_bounded_file_per_scope(tmp_path, fs):
    config_dir = tmp_path / ".hermes"
    adapter = HermesMemoryAdapter(fs, config_dir=config_dir)
    assert adapter.projection_mode is ProjectionMode.RENDER

    project_root = "/work/my-repo"
    # GLOBAL → memories/coffer-global.md; PROJECT → memories/coffer-<slug>.md.
    assert adapter.memory_location(project_root=None, layer=MemoryLayer.GLOBAL) == (
        config_dir / "memories" / "coffer-global.md"
    )
    slug = claude_project_slug(project_root)
    assert adapter.memory_location(project_root=project_root, layer=MemoryLayer.PROJECT) == (
        config_dir / "memories" / f"coffer-{slug}.md"
    )

    memory = _canonical(tmp_path, MemoryLayer.GLOBAL, name="hermes-global")
    result = adapter.establish(memory=memory, project_root=None, agent_ref="hermes")
    target = config_dir / "memories" / "coffer-global.md"
    text = target.read_text(encoding="utf-8")
    assert MANAGED_BLOCK_START in text and "a fact" in text
    assert result.native_memory_disabled is False
    assert result.target_path == str(target)

    adapter.remove(project_root=None, layer=MemoryLayer.GLOBAL)
    assert MANAGED_BLOCK_START not in target.read_text(encoding="utf-8")


def test_default_adapters_registry_modes(fs):
    adapters = default_adapters(fs)
    assert isinstance(adapters[AgentType.OPENCODE], OpenCodeMemoryAdapter)
    assert isinstance(adapters[AgentType.OPENCLAW], OpenClawMemoryAdapter)
    assert isinstance(adapters[AgentType.HERMES], HermesMemoryAdapter)
    assert adapters[AgentType.OPENCODE].projection_mode is ProjectionMode.RENDER
    assert adapters[AgentType.OPENCLAW].projection_mode is ProjectionMode.RENDER
    assert adapters[AgentType.HERMES].projection_mode is ProjectionMode.RENDER
    # Cursor memory is N/A (removed in Cursor 2.1) → stays NONE.
    assert adapters[AgentType.CURSOR].projection_mode is ProjectionMode.NONE


def test_engine_remove_target_by_mode(tmp_path, fs):
    engine = ProjectionEngine(fs)
    # SYMLINK target → unlinked.
    canonical = tmp_path / "canon"
    canonical.mkdir()
    link = tmp_path / "link"
    fs.symlink_with_migrate(canonical_dir=canonical, link_path=link)
    assert link.is_symlink()
    engine.remove_target(mode=ProjectionMode.SYMLINK, target_path=str(link))
    assert not link.exists()
