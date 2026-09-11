"""Codex's model catalogue through the projector, on the real filesystem.

A Codex projection is two files: ``config.toml`` and the Coffer-owned catalogue
it points at via ``model_catalog_json``. The catalogue is what makes Codex's OWN
model picker list the endpoint's models instead of OpenAI's — and because that
key REPLACES Codex's built-in list rather than extending it, de-projection has to
remove both the pointer and the file or the agent keeps offering an endpoint it is
no longer talking to.

The catalogue's field set is pinned in the unit tier (it is a wire contract with
Codex's parser); what these pin down is the file lifecycle.
"""

from __future__ import annotations

import json
import pathlib
import tomllib
from datetime import UTC, datetime

from coffer.application.provider.projector import ProviderProjector
from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol, ProviderConfig
from coffer.domain.provider.projection import CODEX_MODEL_CATALOG_FILENAME
from coffer.domain.resource import Resource
from coffer.infrastructure.agent.config_file_store import ConfigFileStore

_NOW = datetime(2026, 9, 11, tzinfo=UTC)


def _agent(config_dir: pathlib.Path) -> Resource:
    return Resource(
        id=1,
        kind="agent",
        name="cx",
        description=None,
        config={"type": "codex", "config_dir": str(config_dir), "model": "fast"},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _connection(models: list[str]) -> ProviderConfig:
    return ProviderConfig(
        protocol=Protocol.OPENAI,
        base_url="https://gw.example/v1",
        credential_ref="provider/agnes/key",
        compatible_agents=["codex"],
        models=models,
    )


def _projector() -> ProviderProjector:
    return ProviderProjector(ConfigFileStore())


def _catalog(config_dir: pathlib.Path) -> pathlib.Path:
    return config_dir / CODEX_MODEL_CATALOG_FILENAME


def test_activate_then_deactivate_adds_and_retires_the_catalog(tmp_path: pathlib.Path) -> None:
    cfg = tmp_path / ".codex"
    cfg.mkdir()
    (cfg / "config.toml").write_text('# mine\napproval_policy = "never"\n')
    agents = [_agent(cfg)]
    projector = _projector()

    assert projector.project_type(
        "agnes", _connection(["fast", "pro"]), agents, AgentType.CODEX
    ) == ["cx"]
    doc = tomllib.loads((cfg / "config.toml").read_text())
    assert doc["model_catalog_json"] == str(_catalog(cfg))
    assert doc["approval_policy"] == "never"  # the user's own key survives
    models = json.loads(_catalog(cfg).read_text())["models"]
    assert [m["slug"] for m in models] == ["fast", "pro"]

    assert projector.deproject_type(agents, AgentType.CODEX) == ["cx"]
    reverted = tomllib.loads((cfg / "config.toml").read_text())
    assert "model_catalog_json" not in reverted
    assert "model_provider" not in reverted
    assert reverted["approval_policy"] == "never"
    # The file itself is gone, so Codex's built-in model list is back.
    assert not _catalog(cfg).exists()


def test_an_uncurated_connection_leaves_codex_own_model_list_alone(
    tmp_path: pathlib.Path,
) -> None:
    cfg = tmp_path / ".codex"
    cfg.mkdir()
    agents = [_agent(cfg)]

    _projector().project_type("agnes", _connection([]), agents, AgentType.CODEX)

    doc = tomllib.loads((cfg / "config.toml").read_text())
    assert doc["model_provider"] == "coffer"  # the connection IS projected …
    assert "model_catalog_json" not in doc  # … but Codex keeps its own models
    assert not _catalog(cfg).exists()


def test_clearing_the_curated_set_retires_the_catalog_on_reprojection(
    tmp_path: pathlib.Path,
) -> None:
    cfg = tmp_path / ".codex"
    cfg.mkdir()
    agents = [_agent(cfg)]
    projector = _projector()

    projector.project_type("agnes", _connection(["fast"]), agents, AgentType.CODEX)
    assert _catalog(cfg).exists()

    # The user unticks every model: "no restriction" must restore Codex's list
    # rather than leave yesterday's catalogue in force.
    projector.project_type("agnes", _connection([]), agents, AgentType.CODEX)
    assert "model_catalog_json" not in tomllib.loads((cfg / "config.toml").read_text())
    assert not _catalog(cfg).exists()


def test_reprojection_rewrites_only_a_changed_catalog(tmp_path: pathlib.Path) -> None:
    cfg = tmp_path / ".codex"
    cfg.mkdir()
    agents = [_agent(cfg)]
    projector = _projector()

    projector.project_type("agnes", _connection(["fast"]), agents, AgentType.CODEX)
    before = _catalog(cfg).stat().st_mtime_ns

    # Identical projection: the boot sweep re-derives this on every start, and
    # churning the file's mtime would hide a projection that had gone missing.
    projector.project_type("agnes", _connection(["fast"]), agents, AgentType.CODEX)
    assert _catalog(cfg).stat().st_mtime_ns == before

    projector.project_type("agnes", _connection(["fast", "pro"]), agents, AgentType.CODEX)
    models = json.loads(_catalog(cfg).read_text())["models"]
    assert [m["slug"] for m in models] == ["fast", "pro"]


def test_a_user_owned_catalog_is_never_removed(tmp_path: pathlib.Path) -> None:
    cfg = tmp_path / ".codex"
    cfg.mkdir()
    mine = tmp_path / "my-models.json"
    mine.write_text("{}\n")
    (cfg / "config.toml").write_text(f'model_catalog_json = "{mine}"\n')
    agents = [_agent(cfg)]

    # Activating a connection that curates nothing, then reverting to the
    # built-in login, must leave the user's own catalogue pointer untouched.
    projector = _projector()
    projector.project_type("agnes", _connection([]), agents, AgentType.CODEX)
    assert tomllib.loads((cfg / "config.toml").read_text())["model_catalog_json"] == str(mine)

    projector.deproject_type(agents, AgentType.CODEX)
    assert tomllib.loads((cfg / "config.toml").read_text())["model_catalog_json"] == str(mine)
    assert mine.exists()
