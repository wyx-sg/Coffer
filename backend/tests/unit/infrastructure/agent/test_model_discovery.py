"""Unit tests for the on-disk model source and the composite that chains sources.

``NativeConfigModelDiscovery`` reads what each CLI wrote down for itself: Claude
Code caches its picker's extra options in ``.claude.json``; Codex names one
model per profile in ``config.toml``. Every failure path must be an empty list,
never an exception: the catalogue is read on a UI request and on every turn, so
a stray config file must not break either.

``ChainedModelDiscovery`` decides the ORDER the picker shows, and has to survive
one source misbehaving.
"""

from __future__ import annotations

import json
import pathlib

from coffer.domain.agent.model_catalogue import AgentModel
from coffer.infrastructure.agent.model_discovery import (
    ChainedModelDiscovery,
    NativeConfigModelDiscovery,
)

# The real shape Claude Code writes (value/label/description objects).
_CACHE = [
    {
        "value": "claude-fable-5-1[1m]",
        "label": "Fable",
        "description": "Fable 5.1 · Most capable for your hardest and longest-running tasks",
    },
    {"value": "claude-opus-4-9", "label": "Opus", "description": "Opus 4.9"},
]


def _claude_json(path: pathlib.Path, cache: object = _CACHE) -> None:
    path.write_text(
        json.dumps({"numStartups": 12, "additionalModelOptionsCache": cache}),
        encoding="utf-8",
    )


async def test_claude_json_inside_the_config_dir(tmp_path: pathlib.Path) -> None:
    """The CLAUDE_CONFIG_DIR layout keeps ``.claude.json`` inside the dir."""
    config_dir = tmp_path / "custom-claude"
    config_dir.mkdir()
    _claude_json(config_dir / ".claude.json")

    models = await NativeConfigModelDiscovery().discover(
        agent_key="claude_code", config_dir=config_dir
    )

    assert [m.id for m in models] == ["claude-fable-5-1[1m]", "claude-opus-4-9"]
    assert models[0].label == "Fable"
    assert models[0].description.startswith("Fable 5.1")


async def test_claude_json_beside_the_config_dir(tmp_path: pathlib.Path) -> None:
    """The default layout is ``~/.claude`` + ``~/.claude.json`` — one level up."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    _claude_json(tmp_path / ".claude.json")

    models = await NativeConfigModelDiscovery().discover(
        agent_key="claude_code", config_dir=config_dir
    )

    assert [m.id for m in models] == ["claude-fable-5-1[1m]", "claude-opus-4-9"]


async def test_claude_skips_malformed_entries(tmp_path: pathlib.Path) -> None:
    """Non-objects and blank/absent ``value``s are dropped, the rest survive."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    _claude_json(
        tmp_path / ".claude.json",
        cache=["a string", {"label": "no value"}, {"value": "  "}, {"value": "good"}],
    )

    models = await NativeConfigModelDiscovery().discover(
        agent_key="claude_code", config_dir=config_dir
    )

    assert [m.id for m in models] == ["good"]
    # Nothing to read for label/description — they stay empty, not None.
    assert models[0].label == ""
    assert models[0].description == ""


async def test_claude_missing_and_corrupt_files_return_empty(tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    discovery = NativeConfigModelDiscovery()

    assert await discovery.discover(agent_key="claude_code", config_dir=config_dir) == []

    (tmp_path / ".claude.json").write_text("{not json at all", encoding="utf-8")
    assert await discovery.discover(agent_key="claude_code", config_dir=config_dir) == []


async def test_claude_json_without_the_cache_key_returns_empty(tmp_path: pathlib.Path) -> None:
    """Every other key in ``.claude.json`` is ignored (it holds project history,
    onboarding flags, and other state Coffer has no business reading)."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (tmp_path / ".claude.json").write_text(
        json.dumps({"projects": {"/tmp/x": {"history": ["secret"]}}}), encoding="utf-8"
    )

    assert (
        await NativeConfigModelDiscovery().discover(agent_key="claude_code", config_dir=config_dir)
        == []
    )


async def test_codex_config_toml_top_level_and_profiles(tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text(
        """
model = "gpt-5-codex"

[profiles.fast]
model = "gpt-5-mini"

[profiles.broken]
model = 42

[profiles.deep]
model = "o3"
""",
        encoding="utf-8",
    )

    models = await NativeConfigModelDiscovery().discover(agent_key="codex", config_dir=config_dir)

    assert [m.id for m in models] == ["gpt-5-codex", "gpt-5-mini", "o3"]
    assert all(m.label == "" for m in models)


async def test_codex_missing_and_corrupt_config_return_empty(tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    discovery = NativeConfigModelDiscovery()

    assert await discovery.discover(agent_key="codex", config_dir=config_dir) == []

    (config_dir / "config.toml").write_text("model = = =", encoding="utf-8")
    assert await discovery.discover(agent_key="codex", config_dir=config_dir) == []


async def test_unknown_agent_key_returns_empty(tmp_path: pathlib.Path) -> None:
    assert (
        await NativeConfigModelDiscovery().discover(agent_key="hermes", config_dir=tmp_path) == []
    )


async def test_no_registered_agent_means_no_config_to_read() -> None:
    """With no agent of this type registered there is no config dir; this source
    yields nothing and leaves the answer to the sources that ask the CLI."""
    assert (
        await NativeConfigModelDiscovery().discover(agent_key="claude_code", config_dir=None) == []
    )


# ---------------------------------------------------------------------------
# ChainedModelDiscovery
# ---------------------------------------------------------------------------


class _Source:
    """A scripted source that records what it was asked about."""

    def __init__(self, models: list[AgentModel]) -> None:
        self.models = models
        self.calls: list[tuple[str, pathlib.Path | None]] = []

    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        self.calls.append((agent_key, config_dir))
        return list(self.models)


class _Exploding:
    async def discover(
        self, *, agent_key: str, config_dir: pathlib.Path | None
    ) -> list[AgentModel]:
        raise RuntimeError("this source is having a bad day")


async def test_chain_concatenates_in_source_order(tmp_path: pathlib.Path) -> None:
    """The picker's order IS the source order — that is the composite's whole
    job, so it is asserted rather than assumed."""
    first = _Source([AgentModel("a"), AgentModel("b")])
    second = _Source([AgentModel("c")])

    models = await ChainedModelDiscovery([first, second]).discover(
        agent_key="claude_code", config_dir=tmp_path
    )

    assert [m.id for m in models] == ["a", "b", "c"]
    assert first.calls == second.calls == [("claude_code", tmp_path)]


async def test_chain_keeps_duplicates_for_the_service_to_dedupe(tmp_path: pathlib.Path) -> None:
    """Dedupe belongs to the catalogue service (it owns "first wins"), so the
    composite must NOT quietly drop the second copy here."""
    dup = AgentModel("same", "From the binary")
    models = await ChainedModelDiscovery(
        [_Source([dup]), _Source([AgentModel("same", "From the config")])]
    ).discover(agent_key="claude_code", config_dir=tmp_path)

    assert [(m.id, m.label) for m in models] == [
        ("same", "From the binary"),
        ("same", "From the config"),
    ]


async def test_chain_survives_a_source_that_raises(tmp_path: pathlib.Path) -> None:
    survivor = _Source([AgentModel("kept")])

    models = await ChainedModelDiscovery([_Exploding(), survivor]).discover(
        agent_key="codex", config_dir=tmp_path
    )

    assert [m.id for m in models] == ["kept"]


async def test_chain_with_no_sources_is_empty() -> None:
    assert await ChainedModelDiscovery([]).discover(agent_key="codex", config_dir=None) == []
