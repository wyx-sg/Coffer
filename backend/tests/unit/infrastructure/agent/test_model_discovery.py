"""Unit tests for ``NativeConfigModelDiscovery`` — reading the models an agent's
own config advertises.

Claude Code caches its picker's extra options in ``.claude.json``; Codex names
one model per profile in ``config.toml``. Every failure path must be an empty
list, never an exception: the catalogue is read on a UI request and on every
turn, so a stray config file must not break either.
"""

from __future__ import annotations

import json
import pathlib

from coffer.infrastructure.agent.model_discovery import NativeConfigModelDiscovery

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


def test_claude_json_inside_the_config_dir(tmp_path: pathlib.Path) -> None:
    """The CLAUDE_CONFIG_DIR layout keeps ``.claude.json`` inside the dir."""
    config_dir = tmp_path / "custom-claude"
    config_dir.mkdir()
    _claude_json(config_dir / ".claude.json")

    models = NativeConfigModelDiscovery().discover(agent_key="claude_code", config_dir=config_dir)

    assert [m.id for m in models] == ["claude-fable-5-1[1m]", "claude-opus-4-9"]
    assert models[0].label == "Fable"
    assert models[0].description.startswith("Fable 5.1")
    assert {m.source for m in models} == {"discovered"}


def test_claude_json_beside_the_config_dir(tmp_path: pathlib.Path) -> None:
    """The default layout is ``~/.claude`` + ``~/.claude.json`` — one level up."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    _claude_json(tmp_path / ".claude.json")

    models = NativeConfigModelDiscovery().discover(agent_key="claude_code", config_dir=config_dir)

    assert [m.id for m in models] == ["claude-fable-5-1[1m]", "claude-opus-4-9"]


def test_claude_skips_malformed_entries(tmp_path: pathlib.Path) -> None:
    """Non-objects and blank/absent ``value``s are dropped, the rest survive."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    _claude_json(
        tmp_path / ".claude.json",
        cache=["a string", {"label": "no value"}, {"value": "  "}, {"value": "good"}],
    )

    models = NativeConfigModelDiscovery().discover(agent_key="claude_code", config_dir=config_dir)

    assert [m.id for m in models] == ["good"]
    # Nothing to read for label/description — they stay empty, not None.
    assert models[0].label == ""
    assert models[0].description == ""


def test_claude_missing_and_corrupt_files_return_empty(tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    discovery = NativeConfigModelDiscovery()

    assert discovery.discover(agent_key="claude_code", config_dir=config_dir) == []

    (tmp_path / ".claude.json").write_text("{not json at all", encoding="utf-8")
    assert discovery.discover(agent_key="claude_code", config_dir=config_dir) == []


def test_claude_json_without_the_cache_key_returns_empty(tmp_path: pathlib.Path) -> None:
    """Every other key in ``.claude.json`` is ignored (it holds project history,
    onboarding flags, and other state Coffer has no business reading)."""
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    (tmp_path / ".claude.json").write_text(
        json.dumps({"projects": {"/tmp/x": {"history": ["secret"]}}}), encoding="utf-8"
    )

    assert (
        NativeConfigModelDiscovery().discover(agent_key="claude_code", config_dir=config_dir) == []
    )


def test_codex_config_toml_top_level_and_profiles(tmp_path: pathlib.Path) -> None:
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

    models = NativeConfigModelDiscovery().discover(agent_key="codex", config_dir=config_dir)

    assert [m.id for m in models] == ["gpt-5-codex", "gpt-5-mini", "o3"]
    assert all(m.source == "discovered" and m.label == "" for m in models)


def test_codex_missing_and_corrupt_config_return_empty(tmp_path: pathlib.Path) -> None:
    config_dir = tmp_path / ".codex"
    config_dir.mkdir()
    discovery = NativeConfigModelDiscovery()

    assert discovery.discover(agent_key="codex", config_dir=config_dir) == []

    (config_dir / "config.toml").write_text("model = = =", encoding="utf-8")
    assert discovery.discover(agent_key="codex", config_dir=config_dir) == []


def test_unknown_agent_key_returns_empty(tmp_path: pathlib.Path) -> None:
    assert NativeConfigModelDiscovery().discover(agent_key="hermes", config_dir=tmp_path) == []
