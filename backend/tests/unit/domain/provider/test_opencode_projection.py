"""OpenCode's provider projection: ``provider.coffer`` and the top-level
``model`` in ``opencode.json`` (spec provider-switching "Project into OpenCode
config without overwriting it")."""

from __future__ import annotations

import json
import pathlib

import pytest

from coffer.domain.errors import ConfigFileFormatInvalid
from coffer.domain.provider.agent_projection import (
    OpenCodeProviderProjection,
    ProviderProjectionRequest,
    token_file_agents,
)
from coffer.domain.provider.api_key_helper import proxy_token_args, proxy_token_helper
from coffer.domain.provider.codex_projection import CodexAuthCommand
from coffer.domain.provider.model_binding import ModelBinding, ProjectedModel
from coffer.domain.provider.opencode_projection import set_opencode_model

_CFG = pathlib.Path("/home/me/.config/opencode/opencode.json")
_TOKEN = pathlib.Path("/home/me/.coffer/local/proxy-tokens/opencode")


def _req(
    models: tuple[ProjectedModel, ...] = (), *, model: str | None = "m-1", window: int | None = None
) -> ProviderProjectionRequest:
    return ProviderProjectionRequest(
        connection_uid="0" * 32,
        connection_name="agnes",
        agent_uid="a" * 32,
        base_url="http://127.0.0.1:38471/openai/v1",
        key_helper=proxy_token_helper("a" * 32, coffer_cli="/opt/coffer/bin/coffer"),
        codex_auth=CodexAuthCommand("/opt/coffer/bin/coffer", proxy_token_args("a" * 32)),
        binding=ModelBinding(model=model),
        models=models,
        context_window=window,
        token_file=_TOKEN,
    )


_FACET = OpenCodeProviderProjection()


def test_apply_writes_one_provider_reading_its_key_from_the_token_file() -> None:
    user = {"theme": "tokyonight", "provider": {"mine": {"npm": "x"}}, "mcp": {"a": {}}}
    plan = _FACET.apply(
        json.dumps(user),
        _req((ProjectedModel("m-1", 400_000), ProjectedModel("m-2"))),
        _CFG,
    )
    assert plan.before == () and plan.after == ()
    doc = json.loads(plan.text)
    assert doc["theme"] == "tokyonight" and doc["mcp"] == {"a": {}}
    assert doc["provider"]["mine"] == {"npm": "x"}
    coffer = doc["provider"]["coffer"]
    assert coffer["npm"] == "@ai-sdk/openai"
    assert coffer["name"] == "Coffer (agnes)"
    assert coffer["options"] == {
        "baseURL": "http://127.0.0.1:38471/openai/v1",
        "apiKey": "{file:" + str(_TOKEN) + "}",
    }
    assert coffer["models"] == {
        "m-1": {"name": "m-1", "limit": {"context": 400_000, "output": 32_000}},
        "m-2": {"name": "m-2"},
    }
    assert doc["model"] == "coffer/m-1"
    # The key itself never lands in the config.
    assert "cfr_" not in plan.text


def test_an_unrestricted_connection_lists_the_bound_model() -> None:
    doc = json.loads(_FACET.apply("", _req(model="gpt-6", window=8_000), _CFG).text)
    assert doc["provider"]["coffer"]["models"] == {
        "gpt-6": {"name": "gpt-6", "limit": {"context": 8_000, "output": 8_000}}
    }


def test_without_a_binding_coffers_model_goes_and_the_users_stays() -> None:
    ours = json.dumps({"model": "coffer/old"})
    assert "model" not in json.loads(_FACET.apply(ours, _req(model=None), _CFG).text)
    theirs = json.dumps({"model": "anthropic/claude-opus-5-5"})
    doc = json.loads(_FACET.apply(theirs, _req(model=None), _CFG).text)
    assert doc["model"] == "anthropic/claude-opus-5-5"


def test_remove_takes_out_only_what_coffer_wrote() -> None:
    applied = _FACET.apply(json.dumps({"theme": "x"}), _req((ProjectedModel("m-1"),)), _CFG).text
    assert _FACET.is_present(applied)
    removed = _FACET.remove(applied, _CFG).text
    assert json.loads(removed) == {"theme": "x"}
    assert not _FACET.is_present(removed)
    kept = json.dumps({"provider": {"mine": {}}, "model": "mine/a"})
    assert json.loads(_FACET.remove(kept, _CFG).text) == {
        "provider": {"mine": {}},
        "model": "mine/a",
    }


def test_an_empty_file_stays_empty_on_remove() -> None:
    assert _FACET.remove("", _CFG).text == ""
    assert not _FACET.is_present("")


def test_set_native_model_writes_the_provider_qualified_id() -> None:
    assert json.loads(set_opencode_model("{}", "anthropic/claude-opus-5-5")) == {
        "model": "anthropic/claude-opus-5-5"
    }
    assert json.loads(set_opencode_model('{"model": "x/y", "a": 1}', None)) == {"a": 1}


def test_a_file_that_does_not_parse_is_refused() -> None:
    with pytest.raises(ConfigFileFormatInvalid):
        _FACET.apply("{ // comment\n}", _req(), _CFG)


def test_apply_needs_the_token_file() -> None:
    req = _req()
    bare = ProviderProjectionRequest(**{**req.__dict__, "token_file": None})
    with pytest.raises(ValueError):
        _FACET.apply("", bare, _CFG)


def test_only_opencode_reads_its_token_from_a_file() -> None:
    assert token_file_agents() == frozenset({"opencode"})
