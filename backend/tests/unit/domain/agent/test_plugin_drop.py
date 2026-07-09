"""Unit tests for the PLUGIN_DROP file rendering (ADR-042).

The dropped plugin is a self-contained JS module: hook binary + agent name are
embedded as JSON string literals (valid JS for any path), it spawns argv
directly (no shell), caches per session, and is failure-silent.
"""

from __future__ import annotations

import json

from coffer.domain.agent.plugin_drop import (
    PLUGIN_FILENAME,
    PLUGIN_SUBDIR,
    render_plugin,
)


def test_render_embeds_hook_and_agent_as_json_literals() -> None:
    out = render_plugin(hook_binary="/opt/coffer/coffer-hook", agent_name="oc")
    assert 'const HOOK = "/opt/coffer/coffer-hook";' in out
    assert 'const AGENT = "oc";' in out
    # The plugin spawns the raw dialect with the event baked in (stdin is never
    # written to, so coffer-hook must not read it).
    assert '"--dialect", "raw"' in out
    assert '"--event", "sessionStart"' in out
    assert "experimental.chat.system.transform" in out


def test_render_survives_hostile_path_and_name() -> None:
    # A macOS app-bundle path with spaces and quotes must land as ONE valid JS
    # string literal — json.dumps escaping, verified by round-tripping the
    # literal back through a JSON parse.
    hook = '/Apps/My "Best" App/coffer-hook'
    out = render_plugin(hook_binary=hook, agent_name="agent name")
    hook_line = next(line for line in out.splitlines() if line.startswith("const HOOK = "))
    literal = hook_line.removeprefix("const HOOK = ").removesuffix(";")
    assert json.loads(literal) == hook


def test_render_is_deterministic_and_marked() -> None:
    a = render_plugin(hook_binary="/x", agent_name="a")
    assert a == render_plugin(hook_binary="/x", agent_name="a")
    # First line is Coffer's ownership marker — the uninstall contract deletes
    # the file wholesale, so the header must say whose it is.
    assert a.splitlines()[0].startswith("// coffer:session-context")


def test_module_constants() -> None:
    assert PLUGIN_FILENAME == "coffer-session-context.js"
    assert PLUGIN_SUBDIR == "plugin"
