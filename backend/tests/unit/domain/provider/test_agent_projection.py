"""Each agent's provider projection facet: pure plans over the native config
(ADR agent-mechanisms-are-optional-facets-on-the-descriptor)."""

from __future__ import annotations

import json
import pathlib
import tomllib

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.agent_projection import (
    PROVIDER_PROJECTIONS,
    ClaudeCodeProviderProjection,
    CodexProviderProjection,
    ProjectedFile,
    ProviderProjectionRequest,
)

_UID = "0123456789abcdef0123456789abcdef"
_CFG = pathlib.Path("/home/me/.codex/config.toml")


def _req(models: tuple[str, ...] = ()) -> ProviderProjectionRequest:
    return ProviderProjectionRequest(
        connection_uid=_UID,
        connection_name="agnes",
        base_url="https://gw.example/v1",
        model="m-1",
        fast_model=None,
        wire_api=None,
        text_models=models,
        coffer_cli="/opt/coffer/bin/coffer",
    )


def test_each_facet_declares_its_agent_file_and_protocols() -> None:
    by_type = {p.agent_type: p for p in PROVIDER_PROJECTIONS}
    assert set(by_type) == set(AgentType)
    assert by_type[AgentType.CLAUDE_CODE].config_key == "settings"
    assert by_type[AgentType.CLAUDE_CODE].protocols == ("anthropic",)
    assert by_type[AgentType.CODEX].config_key == "config"
    assert by_type[AgentType.CODEX].protocols == ("openai",)


def test_claude_code_plan_is_one_file_naming_the_connection_by_uid() -> None:
    facet = ClaudeCodeProviderProjection()
    plan = facet.apply('{"theme": "dark"}', _req(), pathlib.Path("/h/.claude/settings.json"))
    assert plan.before == () and plan.after == ()
    doc = json.loads(plan.text)
    assert doc["theme"] == "dark"
    assert doc["apiKeyHelper"].endswith(f"--connection-uid {_UID}")
    assert doc["env"]["ANTHROPIC_MODEL"] == "m-1"
    assert facet.is_present(plan.text)
    removed = facet.remove(plan.text, pathlib.Path("/h/.claude/settings.json"))
    assert json.loads(removed.text) == {"theme": "dark", "env": {}}
    assert not facet.is_present(removed.text)


def test_codex_writes_the_catalogue_before_the_pointer() -> None:
    facet = CodexProviderProjection()
    plan = facet.apply("", _req(("m-1", "m-2")), _CFG)
    catalogue = _CFG.parent / "coffer-model-catalog.json"
    assert [f.path for f in plan.before] == [catalogue]
    assert plan.after == ()
    assert tomllib.loads(plan.text)["model_catalog_json"] == str(catalogue)


def test_codex_without_curated_models_retires_the_catalogue_after() -> None:
    plan = CodexProviderProjection().apply("", _req(), _CFG)
    assert plan.before == ()
    assert plan.after == (ProjectedFile(_CFG.parent / "coffer-model-catalog.json", None),)
    assert "model_catalog_json" not in tomllib.loads(plan.text)


def test_codex_removal_drops_the_block_then_the_catalogue() -> None:
    facet = CodexProviderProjection()
    projected = facet.apply('model = "mine"\n', _req(("m-1",)), _CFG).text
    assert facet.is_present(projected)
    removed = facet.remove(projected, _CFG)
    assert not facet.is_present(removed.text)
    assert removed.after == (ProjectedFile(_CFG.parent / "coffer-model-catalog.json", None),)
