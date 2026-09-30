"""Each agent's provider projection facet: pure plans over the native config
(ADR agent-mechanisms-are-optional-facets-on-the-descriptor)."""

from __future__ import annotations

import json
import pathlib
import tomllib

import pytest

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.agent_projection import (
    PROVIDER_PROJECTIONS,
    ClaudeCodeProviderProjection,
    CodexProviderProjection,
    ProjectedFile,
    ProviderProjectionRequest,
)
from coffer.domain.provider.api_key_helper import proxy_token_args, proxy_token_helper
from coffer.domain.provider.codex_projection import CodexAuthCommand
from coffer.domain.provider.model_binding import ModelBinding, ProjectedModel

_UID = "0123456789abcdef0123456789abcdef"
_CFG = pathlib.Path("/home/me/.codex/config.toml")


def _req(
    models: tuple[str, ...] = (), *, binding: ModelBinding | None = None
) -> ProviderProjectionRequest:
    return ProviderProjectionRequest(
        connection_uid=_UID,
        connection_name="agnes",
        agent_uid="a" * 32,
        base_url="https://gw.example/v1",
        key_helper=proxy_token_helper("a" * 32, coffer_cli="/opt/coffer/bin/coffer"),
        codex_auth=CodexAuthCommand("/opt/coffer/bin/coffer", proxy_token_args("a" * 32)),
        binding=binding or ModelBinding(model="m-1"),
        wire_api=None,
        models=tuple(ProjectedModel(id=m) for m in models),
    )


def test_each_facet_declares_its_agent_file_and_protocols() -> None:
    by_type = {p.agent_type: p for p in PROVIDER_PROJECTIONS}
    assert set(by_type) == set(AgentType)
    assert by_type[AgentType.CLAUDE_CODE].config_key == "settings"
    assert by_type[AgentType.CLAUDE_CODE].protocols == ("anthropic",)
    assert by_type[AgentType.CODEX].config_key == "config"
    assert by_type[AgentType.CODEX].protocols == ("openai",)


def test_claude_code_plan_is_one_file_naming_the_agent_by_uid() -> None:
    facet = ClaudeCodeProviderProjection()
    plan = facet.apply('{"theme": "dark"}', _req(), pathlib.Path("/h/.claude/settings.json"))
    assert plan.before == () and plan.after == ()
    doc = json.loads(plan.text)
    assert doc["theme"] == "dark"
    assert doc["apiKeyHelper"].endswith("proxy token --agent-uid " + "a" * 32)
    assert doc["model"] == "m-1"
    # No tier stored: every tier is pinned to the model on a non-Claude endpoint.
    for tier in ("OPUS", "SONNET", "HAIKU"):
        assert doc["env"][f"ANTHROPIC_DEFAULT_{tier}_MODEL"] == "m-1"
    assert facet.is_present(plan.text)
    removed = facet.remove(
        plan.text, pathlib.Path("/h/.claude/settings.json"), ModelBinding(model="m-1")
    )
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


def test_codex_writes_effort_only_for_a_model_with_levels() -> None:
    facet = CodexProviderProjection()
    leveled = ProviderProjectionRequest(
        **{
            **_req().__dict__,
            "binding": ModelBinding(model="m-1", effort="high"),
            "models": (ProjectedModel(id="m-1", effort_levels=("low", "high")),),
        }
    )
    assert tomllib.loads(facet.apply("", leveled, _CFG).text)["model_reasoning_effort"] == "high"
    bare = ProviderProjectionRequest(
        **{**_req(("m-1",)).__dict__, "binding": ModelBinding(model="m-1", effort="high")}
    )
    assert "model_reasoning_effort" not in tomllib.loads(facet.apply("", bare, _CFG).text)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a local connection sets Claude Code's compatibility key",
)
def test_a_local_connection_sets_claude_codes_compatibility_keys() -> None:
    req = ProviderProjectionRequest(
        **{
            **_req().__dict__,
            "binding": ModelBinding(model="qwen"),
            "models": (ProjectedModel(id="qwen", context_window=131072),),
            "local": True,
        }
    )
    env = json.loads(ClaudeCodeProviderProjection().apply("", req, _CFG).text)["env"]
    assert env["CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"] == "1"
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "131072"
    assert {env[f"ANTHROPIC_DEFAULT_{t}_MODEL"] for t in ("OPUS", "SONNET", "HAIKU")} == {"qwen"}
