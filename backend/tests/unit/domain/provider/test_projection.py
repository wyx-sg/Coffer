"""Pure projection-transform tests (spec provider-switching). No I/O — unit tier."""

from __future__ import annotations

import json
import pathlib
import tomllib

import pytest

from coffer.domain.connection import CODEX_ENV_KEY
from coffer.domain.provider.codex_projection import CodexAuthCommand
from coffer.domain.provider.projection import (
    CODEX_PROVIDER_ID,
    anthropic_api_key_helper,
    apply_anthropic_settings,
    apply_codex_provider,
    codex_model_catalog_json,
    codex_model_catalog_path,
    is_managed_api_key_helper,
    remove_anthropic_settings,
    remove_codex_provider,
)

#: ``apply_anthropic_settings`` takes no default helper any more (only the
#: per-connection form may be written), so tests that do not care WHICH
#: connection it names pass this one.
_HELPER = "/opt/coffer/bin/coffer provider key --connection-uid 0123456789abcdef0123456789abcdef"

#: Where the caller resolved the ``coffer`` CLI to.
_CLI = "/Users/me/.coffer/bin/coffer"

#: A connection's uid — what the projected helper resolves. Opaque and, unlike
#: the name it replaced, unchanged by anything the user does to the connection.
_CONNECTION_UID = "7d4f1e2a3b4c5d6e7f8091a2b3c4d5e6"


def test_anthropic_sets_managed_keys_and_preserves_others() -> None:
    out = apply_anthropic_settings(
        '{"theme": "dark", "env": {"FOO": "1"}}',
        base_url="https://gw/anthropic",
        model="claude-opus-4-8",
        effort="high",
        tier_models={"haiku": "claude-haiku-4-5", "opus": "claude-opus-4-8"},
        api_key_helper=anthropic_api_key_helper(_CONNECTION_UID, coffer_cli=_CLI),
    )
    d = json.loads(out)
    assert d["apiKeyHelper"] == anthropic_api_key_helper(_CONNECTION_UID, coffer_cli=_CLI)
    assert d["theme"] == "dark"  # unrelated key preserved
    assert d["env"]["FOO"] == "1"  # unrelated env preserved
    assert d["env"]["ANTHROPIC_BASE_URL"] == "https://gw/anthropic"
    # The top-level keys /model and /effort save to — never env.ANTHROPIC_MODEL,
    # which would outrank the user's own /model choice at every launch.
    assert d["model"] == "claude-opus-4-8"
    assert d["effortLevel"] == "high"
    assert "ANTHROPIC_MODEL" not in d["env"]
    assert d["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "claude-haiku-4-5"
    assert d["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "claude-opus-4-8"
    assert "ANTHROPIC_DEFAULT_SONNET_MODEL" not in d["env"]
    assert "ANTHROPIC_API_KEY" not in d["env"]  # never write the raw key


@pytest.mark.acceptance(
    spec="provider-switching", scenario="every write deletes the deprecated background-model key"
)
def test_every_write_deletes_the_deprecated_model_keys() -> None:
    out = apply_anthropic_settings(
        '{"env": {"ANTHROPIC_SMALL_FAST_MODEL": "stale", "ANTHROPIC_MODEL": "old"}}',
        base_url="u",
        model="m",
        tier_models={"haiku": "h"},
        api_key_helper=_HELPER,
    )
    d = json.loads(out)
    assert "ANTHROPIC_SMALL_FAST_MODEL" not in d["env"]
    assert "ANTHROPIC_MODEL" not in d["env"]
    assert d["model"] == "m"
    assert d["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "h"


def test_anthropic_handles_empty_and_is_idempotent() -> None:
    first = apply_anthropic_settings(
        "", base_url="u", model="m", tier_models={"haiku": "f"}, api_key_helper=_HELPER
    )
    assert json.loads(first)["env"]["ANTHROPIC_BASE_URL"] == "u"
    second = apply_anthropic_settings(
        first, base_url="u", model="m", tier_models={"haiku": "f"}, api_key_helper=_HELPER
    )
    assert json.loads(first) == json.loads(second)


def test_codex_sets_provider_block_and_preserves_others() -> None:
    out = apply_codex_provider(
        'approval_policy = "never"\n',
        base_url="https://gw/v1",
        model="gpt-x",
        wire_api="responses",
        display_name="Coffer (acme)",
    )
    doc = tomllib.loads(out)
    assert doc["approval_policy"] == "never"  # unrelated key preserved
    assert doc["model"] == "gpt-x"
    assert doc["model_provider"] == CODEX_PROVIDER_ID
    block = doc["model_providers"][CODEX_PROVIDER_ID]
    assert block["base_url"] == "https://gw/v1"
    assert block["wire_api"] == "responses"
    assert block["env_key"] == CODEX_ENV_KEY
    assert block["name"] == "Coffer (acme)"


def test_codex_handles_empty_and_is_idempotent() -> None:
    first = apply_codex_provider(
        "", base_url="u", model="m", wire_api="responses", display_name="x"
    )
    second = apply_codex_provider(
        first, base_url="u", model="m", wire_api="responses", display_name="x"
    )
    assert tomllib.loads(first) == tomllib.loads(second)


# --- de-projection (use-built-in: remove Coffer's managed keys) ----------------


def test_remove_anthropic_clears_managed_keys_preserves_others() -> None:
    text = apply_anthropic_settings(
        '{"theme": "dark", "env": {"FOO": "1"}}',
        base_url="u",
        model="m",
        effort="high",
        tier_models={"opus": "m", "sonnet": "m", "haiku": "m"},
        picker_models=("m",),
        replace_builtin_picker=True,
        local=True,
        local_context_window=131072,
        api_key_helper=_HELPER,
    )
    d = json.loads(remove_anthropic_settings(text, managed_model="m", managed_effort="high"))
    assert "apiKeyHelper" not in d  # Coffer's managed helper removed
    assert d["theme"] == "dark"  # unrelated key preserved
    assert d["env"] == {"FOO": "1"}  # unrelated env preserved, every Coffer key gone
    for k in ("model", "effortLevel", "modelPicker"):
        assert k not in d


def test_remove_anthropic_keeps_a_model_the_user_picked_later() -> None:
    text = apply_anthropic_settings(
        "", base_url="u", model="m", effort="high", api_key_helper=_HELPER
    )
    doc = json.loads(text)
    doc["model"] = "opus"  # the user's own /model choice since
    d = json.loads(
        remove_anthropic_settings(json.dumps(doc), managed_model="m", managed_effort="high")
    )
    assert d["model"] == "opus"
    assert "effortLevel" not in d


def test_remove_anthropic_keeps_a_user_owned_model_picker() -> None:
    mine = {"options": [{"model": "opus", "label": "Opus"}], "replaceBuiltInOptions": False}
    d = json.loads(remove_anthropic_settings(json.dumps({"modelPicker": mine})))
    assert d["modelPicker"] == mine


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
        apply_anthropic_settings("", base_url="u", model="m", api_key_helper=_HELPER)
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


# --- the key never reaches the agent's shell commands --------------------------


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the projected key is hidden from the agent's shell commands",
)
def test_the_proxy_form_names_no_key_and_drops_an_earlier_exclude() -> None:
    """Codex fetches its local proxy token through the ``auth`` command, so no
    key rides its environment and the exclusion an earlier build added goes."""
    earlier = '[shell_environment_policy]\nexclude = ["AWS_*", "COFFER_PROVIDER_KEY"]\n'
    out = apply_codex_provider(
        earlier,
        base_url="http://127.0.0.1:8001/openai/v1",
        model="m",
        wire_api="responses",
        display_name="x",
        auth=CodexAuthCommand("/opt/coffer", ("proxy", "token", "--agent-uid", "a1")),
    )
    doc = tomllib.loads(out)
    block = doc["model_providers"][CODEX_PROVIDER_ID]
    assert "env_key" not in block
    assert block["auth"] == {
        "command": "/opt/coffer",
        "args": ["proxy", "token", "--agent-uid", "a1"],
    }
    assert block["supports_websockets"] is False and block["requires_openai_auth"] is False
    assert doc["shell_environment_policy"] == {"exclude": ["AWS_*"]}


def test_codex_excludes_the_key_from_shell_commands() -> None:
    doc = tomllib.loads(
        apply_codex_provider("", base_url="u", model="m", wire_api="responses", display_name="x")
    )
    assert doc["shell_environment_policy"] == {"exclude": [CODEX_ENV_KEY]}


def test_codex_exclude_keeps_the_users_policy_and_adds_the_key_once() -> None:
    text = '[shell_environment_policy]\ninherit = "core"\nexclude = ["AWS_*"]\n'
    once = apply_codex_provider(
        text, base_url="u", model="m", wire_api="responses", display_name="x"
    )
    twice = apply_codex_provider(
        once, base_url="u", model="m", wire_api="responses", display_name="x"
    )
    policy = tomllib.loads(twice)["shell_environment_policy"]
    assert policy == {"inherit": "core", "exclude": ["AWS_*", CODEX_ENV_KEY]}


def test_remove_codex_drops_only_its_own_exclude_entry() -> None:
    projected = apply_codex_provider(
        '[shell_environment_policy]\nexclude = ["AWS_*"]\n',
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
    )
    doc = tomllib.loads(remove_codex_provider(projected))
    assert doc["shell_environment_policy"] == {"exclude": ["AWS_*"]}

    bare = apply_codex_provider("", base_url="u", model="m", wire_api="responses", display_name="x")
    assert "shell_environment_policy" not in tomllib.loads(remove_codex_provider(bare))


def test_per_connection_api_key_helper_is_written_and_removed() -> None:
    # The helper names the connection by UID, which is what makes a rename cost
    # nothing: the line Coffer writes into somebody else's config file goes on
    # resolving after the user relabels the connection, so there is no
    # re-projection to perform and no window in which the agent shells out to a
    # name that no longer exists.
    helper = anthropic_api_key_helper(_CONNECTION_UID, coffer_cli=_CLI)
    assert helper == f"{_CLI} provider key --connection-uid {_CONNECTION_UID}"
    out = apply_anthropic_settings("", base_url="https://agnes", model=None, api_key_helper=helper)
    assert json.loads(out)["apiKeyHelper"] == helper
    # Removal strips ANY Coffer-managed helper, so use-builtin always reverts
    # cleanly — including the forms Coffer no longer writes but did write into
    # files that are still on this disk.
    assert "apiKeyHelper" not in json.loads(remove_anthropic_settings(out))
    for superseded in (
        f"coffer provider key --connection-uid {_CONNECTION_UID}",
        "coffer provider key --wire anthropic",
        "coffer provider key --connection agnes",
    ):
        doc = json.dumps({"apiKeyHelper": superseded})
        assert "apiKeyHelper" not in json.loads(remove_anthropic_settings(doc))


def test_api_key_helper_names_the_cli_by_absolute_path_and_quotes_spaces() -> None:
    """A Dock-launched Claude Code has no login-shell ``PATH``, so the CLI is
    named by path; Claude Code runs the line through a shell, so a space in
    that path must not split it."""
    helper = anthropic_api_key_helper(_CONNECTION_UID, coffer_cli="/Users/me/My Apps/coffer")
    assert helper == f"'/Users/me/My Apps/coffer' provider key --connection-uid {_CONNECTION_UID}"
    assert is_managed_api_key_helper(helper)
    doc = json.dumps({"apiKeyHelper": helper, "theme": "dark"})
    assert json.loads(remove_anthropic_settings(doc)) == {"theme": "dark"}


@pytest.mark.parametrize(
    "helper",
    [
        "my-own-helper --token",
        "/usr/local/bin/op read op://vault/anthropic",
        "coffer-helper provider key",  # program is not the coffer CLI
        "/opt/coffer/bin/coffer provider list",  # not the key command
        "coffer provider",  # too short to be ours
        "'/unbalanced/coffer provider key",  # not a line Coffer could write
        "",
    ],
)
def test_a_user_owned_helper_is_never_claimed(helper: str) -> None:
    assert not is_managed_api_key_helper(helper)
    doc = json.dumps({"apiKeyHelper": helper})
    assert json.loads(remove_anthropic_settings(doc)) == {"apiKeyHelper": helper}


# --- Codex model catalogue (``model_catalog_json``) -----------------------------

# The catalogue file is a WIRE CONTRACT with another program: Codex's parser
# rejects the document if any of these is missing, and then falls back to its
# built-in model list — so the projection silently does not take effect. Verified
# against Codex 0.139.0.
_REQUIRED_CATALOG_FIELDS = {
    "slug",
    "display_name",
    "supported_reasoning_levels",
    "shell_type",
    "visibility",
    "supported_in_api",
    "priority",
    "base_instructions",
    "supports_reasoning_summaries",
    "support_verbosity",
    "truncation_policy",
    "supports_parallel_tool_calls",
    "experimental_supported_tools",
}


def test_catalog_emits_exactly_the_fields_codex_requires() -> None:
    text = codex_model_catalog_json(["m-one", "m-two"])
    assert text is not None
    doc = json.loads(text)
    assert set(doc) == {"models"}
    for entry in doc["models"]:
        assert set(entry) == _REQUIRED_CATALOG_FIELDS


def test_catalog_describes_each_curated_model_in_curated_order() -> None:
    text = codex_model_catalog_json(["fast", "pro"])
    assert text is not None
    models = json.loads(text)["models"]
    assert [m["slug"] for m in models] == ["fast", "pro"]
    # The id is the display name — Coffer authors no model labels of its own.
    assert [m["display_name"] for m in models] == ["fast", "pro"]
    # Codex orders by ascending priority, so the curated order is the index.
    assert [m["priority"] for m in models] == [0, 1]


def test_catalog_claims_only_what_coffer_can_know() -> None:
    text = codex_model_catalog_json(["m"])
    assert text is not None
    entry = json.loads(text)["models"][0]
    assert entry["visibility"] == "list"  # the point is to appear in the picker
    assert entry["supported_in_api"] is True  # curated for an API endpoint
    # Capabilities Coffer cannot derive for a third-party endpoint claim nothing,
    # so Codex sends no reasoning/verbosity/parallel-tool parameters for them.
    assert entry["supported_reasoning_levels"] == []
    assert entry["supports_reasoning_summaries"] is False
    assert entry["support_verbosity"] is False
    assert entry["supports_parallel_tool_calls"] is False
    assert entry["experimental_supported_tools"] == []
    assert entry["shell_type"] == "default"
    assert entry["base_instructions"] == ""
    # Tool-output truncation is a property of Codex's harness, not the endpoint,
    # so it mirrors the built-in catalogue rather than guessing a context window.
    assert entry["truncation_policy"] == {"mode": "tokens", "limit": 10000}


def test_no_catalog_without_a_curated_model_set() -> None:
    # An empty set means "no restriction". A catalogue REPLACES Codex's built-in
    # list, so writing one here would replace it with a guess.
    assert codex_model_catalog_json([]) is None


def test_catalog_path_sits_next_to_config_toml() -> None:
    assert codex_model_catalog_path(pathlib.Path("/home/u/.codex")) == pathlib.Path(
        "/home/u/.codex/coffer-model-catalog.json"
    )


def test_codex_points_at_an_absolute_catalog_path() -> None:
    out = apply_codex_provider(
        "",
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    value = tomllib.loads(out)["model_catalog_json"]
    assert value == "/home/u/.codex/coffer-model-catalog.json"
    assert pathlib.PurePosixPath(value).is_absolute()


def test_codex_rejects_a_relative_catalog_path() -> None:
    # Codex resolves the key as an absolute path; a relative one would resolve
    # against whatever cwd the agent happened to start in.
    with pytest.raises(ValueError, match="must be absolute"):
        apply_codex_provider(
            "",
            base_url="u",
            model="m",
            wire_api="responses",
            display_name="x",
            catalog_path=pathlib.Path(".codex/coffer-model-catalog.json"),
        )


def test_codex_drops_a_stale_coffer_catalog_when_the_set_is_cleared() -> None:
    projected = apply_codex_provider(
        "",
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    cleared = apply_codex_provider(
        projected, base_url="u", model="m", wire_api="responses", display_name="x"
    )
    assert "model_catalog_json" not in tomllib.loads(cleared)


def test_codex_keeps_a_user_owned_catalog_when_it_curates_nothing() -> None:
    out = apply_codex_provider(
        'model_catalog_json = "/home/u/my-models.json"\n',
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
    )
    assert tomllib.loads(out)["model_catalog_json"] == "/home/u/my-models.json"


def test_remove_codex_drops_the_coffer_catalog() -> None:
    text = apply_codex_provider(
        "",
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    # Gone → Codex's own model list is what its picker shows again.
    assert "model_catalog_json" not in tomllib.loads(remove_codex_provider(text))


def test_remove_codex_keeps_a_user_owned_catalog() -> None:
    # Matched by the Coffer-owned filename, exactly as ``apiKeyHelper`` is matched
    # by its managed prefix: a catalogue the user wrote is never removed.
    doc = tomllib.loads(
        remove_codex_provider('model_catalog_json = "/home/u/catalog.json"\napproval = "never"\n')
    )
    assert doc["model_catalog_json"] == "/home/u/catalog.json"
    assert doc["approval"] == "never"


def test_catalog_projection_preserves_comments_and_ordering() -> None:
    original = '# my codex config\napproval_policy = "never"\nsandbox_mode = "read-only"\n'
    out = apply_codex_provider(
        original,
        base_url="u",
        model="m",
        wire_api="responses",
        display_name="x",
        catalog_path=pathlib.Path("/home/u/.codex/coffer-model-catalog.json"),
    )
    assert out.startswith(
        '# my codex config\napproval_policy = "never"\nsandbox_mode = "read-only"'
    )
    reverted = remove_codex_provider(out)
    # Round-trip leaves the user's file as it was, down to the comment (tomlkit's
    # re-serialisation leaves the blank line the removed table stood on).
    assert reverted.strip() == original.strip()
