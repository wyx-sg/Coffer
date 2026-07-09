"""Unit tests for the openclaw PLUGIN_DROP extension package (ADR-043 / FR-048).

The extension is a package DIRECTORY (package.json + openclaw.plugin.json +
index.js) rendered from embedded JSON string literals, plus the fail-closed
``plugins.entries.<id>.enabled`` transforms over openclaw.json. The `node
--check` syntax gate on the rendered entry lives in the integration tier
(``tests/integration/agent/test_openclaw_plugin_js.py`` — it spawns a process).
"""

from __future__ import annotations

import json

from coffer.domain.agent.plugin_drop_openclaw import (
    OPENCLAW_ENTRY_FILENAME,
    OPENCLAW_EXTENSIONS_SUBDIR,
    OPENCLAW_PLUGIN_ID,
    apply_entry_enable,
    apply_entry_remove,
    has_entry,
    is_entry_enabled,
    render_openclaw_extension,
)


def test_render_produces_the_three_package_files() -> None:
    files = render_openclaw_extension(hook_binary="/opt/coffer/coffer-hook", agent_name="ow")
    assert set(files) == {"package.json", "openclaw.plugin.json", OPENCLAW_ENTRY_FILENAME}

    pkg = json.loads(files["package.json"])
    assert pkg["name"] == OPENCLAW_PLUGIN_ID
    # openclaw discovers the entry module through this field.
    assert pkg["openclaw"] == {"extensions": ["./index.js"]}

    manifest = json.loads(files["openclaw.plugin.json"])
    assert manifest["id"] == OPENCLAW_PLUGIN_ID
    assert manifest["configSchema"] == {"type": "object", "additionalProperties": False}


def test_render_entry_embeds_hook_and_agent_as_json_literals() -> None:
    entry = render_openclaw_extension(hook_binary="/opt/coffer/coffer-hook", agent_name="ow")[
        OPENCLAW_ENTRY_FILENAME
    ]
    assert 'const HOOK = "/opt/coffer/coffer-hook";' in entry
    assert 'const AGENT = "ow";' in entry
    # The plugin spawns the raw dialect with the event baked in (stdin is never
    # written to, so coffer-hook must not read it).
    assert '"--dialect", "raw"' in entry
    assert '"--event", "sessionStart"' in entry
    # openclaw's prompt-injection hook + its return contract.
    assert 'api.on("before_prompt_build"' in entry
    assert "appendSystemContext" in entry
    assert 'from "openclaw/plugin-sdk/plugin-entry"' in entry


def test_render_survives_hostile_path_and_name() -> None:
    hook = '/Apps/My "Best" App/coffer-hook'
    entry = render_openclaw_extension(hook_binary=hook, agent_name="agent name")[
        OPENCLAW_ENTRY_FILENAME
    ]
    hook_line = next(line for line in entry.splitlines() if line.startswith("const HOOK = "))
    literal = hook_line.removeprefix("const HOOK = ").removesuffix(";")
    assert json.loads(literal) == hook


def test_render_is_deterministic_and_marked() -> None:
    a = render_openclaw_extension(hook_binary="/x", agent_name="a")
    assert a == render_openclaw_extension(hook_binary="/x", agent_name="a")
    # First line is Coffer's ownership marker — uninstall deletes the whole
    # package, so the header must say whose it is.
    assert a[OPENCLAW_ENTRY_FILENAME].splitlines()[0].startswith("// coffer:session-context")


def test_module_constants() -> None:
    assert OPENCLAW_PLUGIN_ID == "coffer-session-context"
    assert OPENCLAW_EXTENSIONS_SUBDIR == "extensions"
    assert OPENCLAW_ENTRY_FILENAME == "index.js"


# --- openclaw.json enable-flag transforms ---------------------------------------


def test_enable_creates_the_chain_and_is_idempotent() -> None:
    out = apply_entry_enable("")
    data = json.loads(out)
    assert data["plugins"]["entries"][OPENCLAW_PLUGIN_ID] == {"enabled": True}
    assert is_entry_enabled(out) is True
    assert has_entry(out) is True
    assert json.loads(apply_entry_enable(out)) == data  # idempotent


def test_enable_preserves_unrelated_plugin_entries_and_keys() -> None:
    seed = json.dumps(
        {
            "gateway": {"port": 18789},
            "plugins": {"entries": {"memory-core": {"enabled": False}}, "slots": {"memory": "x"}},
        }
    )
    data = json.loads(apply_entry_enable(seed))
    assert data["gateway"] == {"port": 18789}
    assert data["plugins"]["entries"]["memory-core"] == {"enabled": False}
    assert data["plugins"]["slots"] == {"memory": "x"}
    assert data["plugins"]["entries"][OPENCLAW_PLUGIN_ID]["enabled"] is True


def test_remove_is_a_true_inverse_and_tidies_empty_containers() -> None:
    out = apply_entry_remove(apply_entry_enable(""))
    assert json.loads(out) == {}
    assert has_entry(out) is False


def test_remove_keeps_non_empty_containers() -> None:
    seed = apply_entry_enable(json.dumps({"plugins": {"entries": {"other": {"enabled": True}}}}))
    data = json.loads(apply_entry_remove(seed))
    assert data["plugins"]["entries"] == {"other": {"enabled": True}}


def test_has_entry_and_is_enabled_tolerate_odd_shapes() -> None:
    assert has_entry("") is False
    assert is_entry_enabled("") is False
    assert has_entry(json.dumps({"plugins": "x"})) is False
    assert is_entry_enabled(json.dumps({"plugins": {"entries": {OPENCLAW_PLUGIN_ID: True}}})) is (
        False
    )
