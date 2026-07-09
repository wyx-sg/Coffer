"""Pure projection-transform tests (spec 011). No I/O — unit tier."""

from __future__ import annotations

import json
import tomllib

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol
from coffer.domain.provider.projection import (
    ANTHROPIC_API_KEY_HELPER,
    CODEX_ENV_KEY,
    CODEX_PROVIDER_ID,
    anthropic_api_key_helper,
    apply_anthropic_settings,
    apply_codex_provider,
    remove_anthropic_settings,
    remove_codex_provider,
    target_for,
    target_for_agent,
)


def test_anthropic_sets_managed_keys_and_preserves_others() -> None:
    out = apply_anthropic_settings(
        '{"theme": "dark", "env": {"FOO": "1"}}',
        base_url="https://gw/anthropic",
        model="claude-opus-4-8",
        fast_model="claude-haiku-4-5",
    )
    d = json.loads(out)
    assert d["apiKeyHelper"] == ANTHROPIC_API_KEY_HELPER
    assert d["theme"] == "dark"  # unrelated key preserved
    assert d["env"]["FOO"] == "1"  # unrelated env preserved
    assert d["env"]["ANTHROPIC_BASE_URL"] == "https://gw/anthropic"
    assert d["env"]["ANTHROPIC_MODEL"] == "claude-opus-4-8"
    assert d["env"]["ANTHROPIC_SMALL_FAST_MODEL"] == "claude-haiku-4-5"
    assert "ANTHROPIC_API_KEY" not in d["env"]  # never write the raw key


def test_anthropic_omits_fast_model_when_none() -> None:
    out = apply_anthropic_settings(
        '{"env": {"ANTHROPIC_SMALL_FAST_MODEL": "stale"}}',
        base_url="u",
        model="m",
        fast_model=None,
    )
    assert "ANTHROPIC_SMALL_FAST_MODEL" not in json.loads(out)["env"]


def test_anthropic_handles_empty_and_is_idempotent() -> None:
    first = apply_anthropic_settings("", base_url="u", model="m", fast_model="f")
    assert json.loads(first)["env"]["ANTHROPIC_BASE_URL"] == "u"
    second = apply_anthropic_settings(first, base_url="u", model="m", fast_model="f")
    assert json.loads(first) == json.loads(second)


def test_codex_sets_provider_block_and_preserves_others() -> None:
    out = apply_codex_provider(
        'approval_policy = "never"\n',
        base_url="https://gw/v1",
        model="gpt-x",
        wire_api="chat",
        display_name="Coffer (acme)",
    )
    doc = tomllib.loads(out)
    assert doc["approval_policy"] == "never"  # unrelated key preserved
    assert doc["model"] == "gpt-x"
    assert doc["model_provider"] == CODEX_PROVIDER_ID
    block = doc["model_providers"][CODEX_PROVIDER_ID]
    assert block["base_url"] == "https://gw/v1"
    assert block["wire_api"] == "chat"
    assert block["env_key"] == CODEX_ENV_KEY
    assert block["name"] == "Coffer (acme)"


def test_codex_handles_empty_and_is_idempotent() -> None:
    first = apply_codex_provider("", base_url="u", model="m", wire_api="chat", display_name="x")
    second = apply_codex_provider(first, base_url="u", model="m", wire_api="chat", display_name="x")
    assert tomllib.loads(first) == tomllib.loads(second)


# --- de-projection (use-built-in: remove Coffer's managed keys) ----------------


def test_remove_anthropic_clears_managed_keys_preserves_others() -> None:
    text = apply_anthropic_settings(
        '{"theme": "dark", "env": {"FOO": "1"}}',
        base_url="u",
        model="m",
        fast_model="f",
    )
    d = json.loads(remove_anthropic_settings(text))
    assert "apiKeyHelper" not in d  # Coffer's managed helper removed
    assert d["theme"] == "dark"  # unrelated key preserved
    assert d["env"]["FOO"] == "1"  # unrelated env preserved
    for k in ("ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL"):
        assert k not in d["env"]


def test_remove_anthropic_keeps_a_user_owned_apikeyhelper() -> None:
    d = json.loads(
        remove_anthropic_settings(
            '{"apiKeyHelper": "my-own-helper", "env": {"ANTHROPIC_BASE_URL": "u"}}'
        )
    )
    assert d["apiKeyHelper"] == "my-own-helper"  # only Coffer's managed helper is cleared
    assert "ANTHROPIC_BASE_URL" not in d["env"]


def test_remove_anthropic_empty_and_idempotent() -> None:
    assert json.loads(remove_anthropic_settings("")) == {}
    once = remove_anthropic_settings(
        apply_anthropic_settings("", base_url="u", model="m", fast_model=None)
    )
    twice = remove_anthropic_settings(once)
    assert json.loads(once) == json.loads(twice)


def test_remove_codex_clears_managed_block_preserves_others() -> None:
    text = apply_codex_provider(
        'approval_policy = "never"\n',
        base_url="u",
        model="gpt-x",
        wire_api="responses",
        display_name="Coffer (acme)",
    )
    doc = tomllib.loads(remove_codex_provider(text))
    assert doc["approval_policy"] == "never"  # unrelated key preserved
    assert "model_provider" not in doc  # Coffer selector removed
    assert "model" not in doc  # Coffer-projected model removed → codex default
    assert CODEX_PROVIDER_ID not in doc.get("model_providers", {})


def test_remove_codex_keeps_a_user_owned_provider() -> None:
    doc = tomllib.loads(
        remove_codex_provider(
            'model_provider = "myown"\nmodel = "x"\n\n[model_providers.myown]\nbase_url = "u"\n'
        )
    )
    # A non-Coffer active provider is left untouched (we only undo our own).
    assert doc["model_provider"] == "myown"
    assert doc["model"] == "x"
    assert "myown" in doc["model_providers"]


def test_remove_codex_empty_and_idempotent() -> None:
    assert remove_codex_provider("").strip() == ""
    once = remove_codex_provider(
        apply_codex_provider("", base_url="u", model="m", wire_api="responses", display_name="x")
    )
    twice = remove_codex_provider(once)
    assert tomllib.loads(once) == tomllib.loads(twice)


def test_targets_map_wire_to_agent() -> None:
    assert target_for(Protocol.ANTHROPIC).agent_type is AgentType.CLAUDE_CODE
    assert target_for(Protocol.ANTHROPIC).config_key == "settings"
    assert target_for(Protocol.OPENAI).agent_type is AgentType.CODEX
    assert target_for(Protocol.OPENAI).config_key == "config"


def test_target_for_agent_maps_agent_to_config() -> None:
    # The projection writer is now chosen by AGENT type, not protocol — so an
    # openai-wire connection routed to Claude Code writes settings.json.
    cc = target_for_agent(AgentType.CLAUDE_CODE)
    assert cc is not None and cc.config_key == "settings"
    cx = target_for_agent(AgentType.CODEX)
    assert cx is not None and cx.config_key == "config"


def test_per_connection_api_key_helper_is_written_and_removed() -> None:
    helper = anthropic_api_key_helper("agnes")
    assert helper == "coffer provider key --connection agnes"
    out = apply_anthropic_settings(
        "", base_url="https://agnes", model=None, fast_model=None, api_key_helper=helper
    )
    assert json.loads(out)["apiKeyHelper"] == helper
    # Removal strips ANY Coffer-managed helper by prefix (per-connection or the
    # legacy --wire form), so use-builtin always reverts cleanly.
    assert "apiKeyHelper" not in json.loads(remove_anthropic_settings(out))
    legacy = '{"apiKeyHelper": "coffer provider key --wire anthropic"}'
    assert "apiKeyHelper" not in json.loads(remove_anthropic_settings(legacy))


# --- opencode (ADR-040) — openai-compatible provider block in opencode.json ----


def test_opencode_provider_writes_block_and_selects_model() -> None:
    from coffer.domain.provider.projection import apply_opencode_provider

    out = apply_opencode_provider('{"theme": "system"}', base_url="https://gw/v1", model="gpt-5")
    d = json.loads(out)
    assert d["theme"] == "system"  # unrelated key preserved
    block = d["provider"][CODEX_PROVIDER_ID]
    assert block["npm"] == "@ai-sdk/openai-compatible"
    assert block["options"]["baseURL"] == "https://gw/v1"
    # The raw key is never written — only an {env:...} reference.
    assert block["options"]["apiKey"] == f"{{env:{CODEX_ENV_KEY}}}"
    assert "gpt-5" in block["models"]
    assert d["model"] == f"{CODEX_PROVIDER_ID}/gpt-5"


def test_opencode_provider_unbound_model_leaves_top_level_model() -> None:
    from coffer.domain.provider.projection import apply_opencode_provider

    out = apply_opencode_provider('{"model": "user/own"}', base_url="https://gw/v1", model=None)
    d = json.loads(out)
    assert d["model"] == "user/own"  # untouched when the agent is unbound
    assert "provider" in d


def test_opencode_provider_unbound_clears_stale_coffer_model() -> None:
    from coffer.domain.provider.projection import apply_opencode_provider

    # A previously-bound file carries model="coffer/gpt-5"; re-projecting unbound
    # must clear it (parity with Codex) so opencode uses its own default rather
    # than a stale coffer model whose models map is now empty.
    text = json.dumps(
        {"model": f"{CODEX_PROVIDER_ID}/gpt-5", "provider": {CODEX_PROVIDER_ID: {"npm": "x"}}}
    )
    out = apply_opencode_provider(text, base_url="https://gw/v1", model=None)
    d = json.loads(out)
    assert "model" not in d


def test_opencode_remove_strips_block_and_coffer_model() -> None:
    from coffer.domain.provider.projection import apply_opencode_provider, remove_opencode_provider

    out = apply_opencode_provider('{"keep": 1}', base_url="https://gw/v1", model="gpt-5")
    back = json.loads(remove_opencode_provider(out))
    assert "provider" not in back  # provider object removed once empty
    assert "model" not in back  # coffer/* model cleared
    assert back["keep"] == 1  # unrelated key preserved


def test_opencode_remove_keeps_user_model_and_other_providers() -> None:
    from coffer.domain.provider.projection import remove_opencode_provider

    text = json.dumps(
        {
            "model": "openai/gpt-4o",  # user-chosen, not coffer/*
            "provider": {CODEX_PROVIDER_ID: {"npm": "x"}, "mine": {"npm": "y"}},
        }
    )
    back = json.loads(remove_opencode_provider(text))
    assert back["model"] == "openai/gpt-4o"  # not a coffer/* model → left alone
    assert CODEX_PROVIDER_ID not in back["provider"]
    assert back["provider"]["mine"] == {"npm": "y"}  # other provider preserved


def test_target_for_agent_opencode() -> None:
    t = target_for_agent(AgentType.OPENCODE)
    assert t is not None
    assert t.config_key == "opencode"
    assert t.format.value == "json"


# --- hermes (ADR-040) — YAML provider block in config.yaml ---------------------


def test_hermes_provider_writes_model_and_provider_yaml() -> None:
    import yaml

    from coffer.domain.provider.projection import apply_hermes_provider

    out = apply_hermes_provider("agent:\n  name: h\n", base_url="https://gw/v1", model="hermes-4")
    d = yaml.safe_load(out)
    assert d["agent"]["name"] == "h"  # unrelated key preserved
    assert d["model"]["provider"] == "coffer"
    assert d["model"]["base_url"] == "https://gw/v1"
    assert d["model"]["default"] == "hermes-4"
    # The raw key is never written — only a key_env reference.
    assert d["providers"]["coffer"]["key_env"] == CODEX_ENV_KEY
    assert d["providers"]["coffer"]["default_model"] == "hermes-4"


def test_hermes_provider_unbound_omits_model_default() -> None:
    import yaml

    from coffer.domain.provider.projection import apply_hermes_provider

    d = yaml.safe_load(apply_hermes_provider("", base_url="https://gw/v1", model=None))
    assert "default" not in d["model"]
    assert "default_model" not in d["providers"]["coffer"]


def test_hermes_remove_reverts_only_coffer() -> None:
    import yaml

    from coffer.domain.provider.projection import apply_hermes_provider, remove_hermes_provider

    out = apply_hermes_provider("keep: 1\n", base_url="https://gw/v1", model="hermes-4")
    back = yaml.safe_load(remove_hermes_provider(out))
    assert back["keep"] == 1
    assert "coffer" not in back.get("providers", {})
    assert back.get("model", {}).get("provider") != "coffer"


def test_hermes_remove_keeps_user_provider() -> None:
    import yaml

    from coffer.domain.provider.projection import remove_hermes_provider

    text = (
        "model:\n  provider: mine\n"
        "providers:\n  coffer:\n    base_url: x\n  mine:\n    base_url: y\n"
    )
    back = yaml.safe_load(remove_hermes_provider(text))
    assert back["model"]["provider"] == "mine"  # user provider untouched
    assert "coffer" not in back["providers"]
    assert back["providers"]["mine"]["base_url"] == "y"


def test_target_for_agent_hermes() -> None:
    t = target_for_agent(AgentType.HERMES)
    assert t is not None
    assert t.config_key == "config"
    assert t.format.value == "yaml"


# --- openclaw (ADR-043) — models.providers block in openclaw.json --------------


def test_openclaw_provider_writes_block_and_selects_primary() -> None:
    from coffer.domain.provider.projection_openclaw import apply_openclaw_provider

    seed = json.dumps(
        {
            "gateway": {"port": 18789},
            "agents": {"defaults": {"model": {"fallbacks": ["openrouter/auto"]}}},
        }
    )
    out = apply_openclaw_provider(seed, base_url="https://gw/v1", model="gpt-5")
    d = json.loads(out)
    assert d["gateway"] == {"port": 18789}  # unrelated key preserved
    block = d["models"]["providers"][CODEX_PROVIDER_ID]
    assert block["api"] == "openai-completions"
    assert block["baseUrl"] == "https://gw/v1"
    # The raw key is never written — only a ${...} env reference (a missing var
    # is a startup WARNING for openclaw, probe-verified on 2026.6.11).
    assert block["apiKey"] == f"${{{CODEX_ENV_KEY}}}"
    # A custom provider MUST declare models, each with id AND name (probe:
    # `openclaw config validate` rejects both omissions).
    assert block["models"] == [{"id": "gpt-5", "name": "gpt-5"}]
    model_block = d["agents"]["defaults"]["model"]
    assert model_block["primary"] == f"{CODEX_PROVIDER_ID}/gpt-5"
    assert model_block["fallbacks"] == ["openrouter/auto"]  # PRESERVED


def test_openclaw_provider_anthropic_wire_uses_anthropic_api() -> None:
    from coffer.domain.provider.projection_openclaw import (
        OPENCLAW_API_ANTHROPIC,
        apply_openclaw_provider,
    )

    out = apply_openclaw_provider(
        "",
        base_url="https://api.anthropic.com",
        model="claude-sonnet-4-5",
        api=OPENCLAW_API_ANTHROPIC,
    )
    d = json.loads(out)
    assert d["models"]["providers"][CODEX_PROVIDER_ID]["api"] == "anthropic-messages"


def test_openclaw_provider_unbound_projects_empty_models_and_leaves_primary() -> None:
    from coffer.domain.provider.projection_openclaw import apply_openclaw_provider

    seed = json.dumps({"agents": {"defaults": {"model": {"primary": "user/own"}}}})
    out = apply_openclaw_provider(seed, base_url="https://gw/v1", model=None)
    d = json.loads(out)
    # models: [] is VALID for a custom provider (probe) — the block is inert
    # until a model is bound.
    assert d["models"]["providers"][CODEX_PROVIDER_ID]["models"] == []
    assert d["agents"]["defaults"]["model"]["primary"] == "user/own"  # untouched


def test_openclaw_provider_unbound_clears_stale_coffer_primary() -> None:
    from coffer.domain.provider.projection_openclaw import apply_openclaw_provider

    seed = json.dumps(
        {"agents": {"defaults": {"model": {"primary": f"{CODEX_PROVIDER_ID}/gpt-5"}}}}
    )
    out = apply_openclaw_provider(seed, base_url="https://gw/v1", model=None)
    d = json.loads(out)
    # A stale coffer/* primary is cleared so openclaw runs on its own default.
    assert "agents" not in d or "primary" not in (d["agents"].get("defaults", {}).get("model", {}))


def test_openclaw_remove_reverts_only_coffer() -> None:
    from coffer.domain.provider.projection_openclaw import (
        apply_openclaw_provider,
        remove_openclaw_provider,
    )

    seed = json.dumps(
        {
            "models": {"providers": {"deepseek": {"api": "openai-completions"}}},
            "agents": {"defaults": {"model": {"fallbacks": ["openrouter/auto"]}}},
        }
    )
    out = apply_openclaw_provider(seed, base_url="https://gw/v1", model="gpt-5")
    back = json.loads(remove_openclaw_provider(out))
    assert CODEX_PROVIDER_ID not in back["models"]["providers"]
    assert back["models"]["providers"]["deepseek"] == {"api": "openai-completions"}
    model_block = back["agents"]["defaults"]["model"]
    assert "primary" not in model_block  # coffer/* primary cleared
    assert model_block["fallbacks"] == ["openrouter/auto"]  # PRESERVED


def test_openclaw_remove_keeps_user_primary_and_tidies_empty_containers() -> None:
    from coffer.domain.provider.projection_openclaw import (
        apply_openclaw_provider,
        remove_openclaw_provider,
    )

    # A user-chosen primary (not coffer/*) is left alone.
    seed = json.dumps({"agents": {"defaults": {"model": {"primary": "deepseek/v4"}}}})
    out = apply_openclaw_provider(seed, base_url="https://gw/v1", model=None)
    back = json.loads(remove_openclaw_provider(out))
    assert back["agents"]["defaults"]["model"]["primary"] == "deepseek/v4"
    assert "models" not in back  # the container Coffer created is tidied away

    # Projecting into an empty file and removing leaves an empty document.
    round_trip = remove_openclaw_provider(
        apply_openclaw_provider("", base_url="https://gw/v1", model="m")
    )
    assert json.loads(round_trip) == {}


def test_target_for_agent_openclaw() -> None:
    t = target_for_agent(AgentType.OPENCLAW)
    assert t is not None
    assert t.config_key == "config"
    assert t.format.value == "json"
