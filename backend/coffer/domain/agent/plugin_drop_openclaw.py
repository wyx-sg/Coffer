"""Render Coffer's session-context extension package for openclaw (FR-048).

Pure domain transforms — no filesystem access — the openclaw ``PluginFlavor``
of the ``PLUGIN_DROP`` injection mode (ADR-042 / ADR-044). openclaw discovers a
local plugin as a PACKAGE DIRECTORY in ``~/.openclaw/extensions/<id>/`` holding
(probe-verified on openclaw 2026.6.11):

- ``package.json`` whose ``openclaw.extensions`` array names the entry module;
- ``openclaw.plugin.json`` — the manifest ``{id, configSchema}``;
- the entry module exporting ``definePluginEntry({id, name, register(api)})``
  from ``openclaw/plugin-sdk/plugin-entry``.

Unlike opencode's auto-loaded flat file, a non-bundled openclaw plugin is
FAIL-CLOSED: it also needs ``plugins.entries.<id>.enabled: true`` in
``openclaw.json``, so this module carries the JSON config transforms for that
flag alongside the file rendering. The prompt-injection hook is
``api.on("before_prompt_build", handler)``; the handler RETURNS
``{appendSystemContext: <text>}`` which openclaw appends to the system prompt.

The gateway caveat: a long-running ``openclaw gateway`` loads plugins at
startup, so channel-driven openclaw sessions pick the extension up only after a
gateway restart. Coffer-driven turns use ``openclaw agent --local`` (fully
embedded, plugin registry preloaded per run), which sees the extension
immediately.

The hook binary path and agent name are embedded via ``json.dumps`` (valid JS
string literals for any path); the plugin spawns argv directly (no shell).
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

from coffer.domain.agent.mcp_entries import _parse_json

#: The extension's id — the package directory name under ``extensions/``, the
#: manifest ``id``, and the ``plugins.entries`` key. Coffer's namespace claim.
OPENCLAW_PLUGIN_ID = "coffer-session-context"

#: Subdirectory of the openclaw state dir that local extension packages live in.
OPENCLAW_EXTENSIONS_SUBDIR = "extensions"

#: The entry module inside the package — its presence marks "installed".
OPENCLAW_ENTRY_FILENAME = "index.js"

_PACKAGE_JSON = {
    "name": OPENCLAW_PLUGIN_ID,
    "version": "1.0.0",
    "type": "module",
    "openclaw": {"extensions": ["./index.js"]},
}

_MANIFEST_JSON = {
    "id": OPENCLAW_PLUGIN_ID,
    "configSchema": {"type": "object", "additionalProperties": False},
}

_ENTRY_TEMPLATE = """\
// coffer:session-context — managed by Coffer; do not edit (overwritten on
// reinstall). Remove via the Coffer agent page or `coffer agent hook uninstall`.
// Injects Coffer's rules + memory bundle into every session's system prompt by
// spawning the same coffer-hook binary the shell-hook agents exec.
import {{ definePluginEntry }} from "openclaw/plugin-sdk/plugin-entry";
import {{ spawn }} from "node:child_process";

const HOOK = {hook};
const AGENT = {agent};
// Covers coffer-hook's own 5s HTTP timeout PLUS PyInstaller onefile startup
// (bootloader + extraction can add seconds on a cold run).
const TIMEOUT_MS = 10000;
const cache = new Map();

function fetchContext() {{
  return new Promise((resolve) => {{
    let done = false;
    const settle = (value) => {{
      if (!done) {{ done = true; resolve(value); }}
    }};
    // Hard settle guard: 'close' waits on the stdout pipe, which a killed
    // child's grandchild can hold open past the spawn timeout. Failure must
    // stay silent AND bounded.
    const guard = setTimeout(() => settle(""), TIMEOUT_MS + 1000);
    if (guard.unref) guard.unref();
    let out = "";
    let child;
    try {{
      child = spawn(HOOK, ["--agent", AGENT, "--dialect", "raw", "--event", "sessionStart"], {{
        stdio: ["ignore", "pipe", "ignore"],
        timeout: TIMEOUT_MS,
      }});
    }} catch {{
      settle("");
      return;
    }}
    // Decode as a stream: per-chunk implicit decode would tear a multi-byte
    // UTF-8 char that straddles a chunk boundary into U+FFFD.
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (d) => {{ out += d; }});
    child.on("error", () => settle(""));
    child.on("close", (code) => settle(code === 0 ? out.trim() : ""));
  }});
}}

export default definePluginEntry({{
  id: {plugin_id},
  name: "Coffer session context",
  register(api) {{
    // The event arg is {{prompt, messages}} only; session identity rides on the
    // SECOND handler arg (ctx.sessionKey / ctx.sessionId — openclaw 2026.6.11
    // hook-types). Keying the cache off it means a long-running gateway
    // re-fetches per session instead of pinning one bundle process-wide.
    api.on("before_prompt_build", async (_event, hookCtx) => {{
      // FAILURE-IS-SILENT: a broken daemon must never break the user's agent.
      try {{
        const key =
          (hookCtx && (hookCtx.sessionKey || hookCtx.sessionId)) || "global";
        let ctx = cache.get(key);
        if (ctx === undefined) {{
          ctx = await fetchContext();
          // Cache only success: a transient daemon blip must not pin an empty
          // context for the whole session — retry on the next call instead.
          if (ctx) cache.set(key, ctx);
        }}
        if (ctx) return {{ appendSystemContext: ctx }};
      }} catch {{}}
      return undefined;
    }});
  }},
}});
"""


def render_openclaw_extension(*, hook_binary: str, agent_name: str) -> dict[str, str]:
    """The extension package's files for one agent: filename → content."""
    return {
        "package.json": json.dumps(_PACKAGE_JSON, indent=2) + "\n",
        "openclaw.plugin.json": json.dumps(_MANIFEST_JSON, indent=2) + "\n",
        OPENCLAW_ENTRY_FILENAME: _ENTRY_TEMPLATE.format(
            hook=json.dumps(hook_binary),
            agent=json.dumps(agent_name),
            plugin_id=json.dumps(OPENCLAW_PLUGIN_ID),
        ),
    }


# --- openclaw.json enable-flag transforms ---------------------------------------
# Non-bundled plugins are fail-closed: presence of the package alone does NOT
# load it. Install sets `plugins.entries.<id>.enabled: true`; uninstall removes
# the entry (and the containers Coffer's own write left empty).


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def apply_entry_enable(text: str) -> str:
    """Return new ``openclaw.json`` text with Coffer's extension enabled."""
    data = _parse_json(text)
    plugins = data.get("plugins")
    if not isinstance(plugins, MutableMapping):
        plugins = {}
        data["plugins"] = plugins
    entries = plugins.get("entries")
    if not isinstance(entries, MutableMapping):
        entries = {}
        plugins["entries"] = entries
    entry = entries.get(OPENCLAW_PLUGIN_ID)
    if not isinstance(entry, MutableMapping):
        entry = {}
        entries[OPENCLAW_PLUGIN_ID] = entry
    entry["enabled"] = True
    return _dump(data)


def apply_entry_remove(text: str) -> str:
    """Inverse of :func:`apply_entry_enable` — drop Coffer's ``plugins.entries``
    key, then any ``entries``/``plugins`` container that is left empty (only ever
    tidies containers whose remaining content is Coffer's own removal)."""
    data = _parse_json(text)
    plugins = data.get("plugins")
    if isinstance(plugins, MutableMapping):
        entries = plugins.get("entries")
        if isinstance(entries, MutableMapping):
            entries.pop(OPENCLAW_PLUGIN_ID, None)
            if not entries:
                plugins.pop("entries", None)
        if not plugins:
            data.pop("plugins", None)
    return _dump(data)


def has_entry(text: str) -> bool:
    """Whether Coffer's ``plugins.entries.<id>`` key is present at all (any
    value) — the semantic no-op guard for uninstall, so a file whose only
    difference is formatting is never rewritten or audited."""
    if not text.strip():
        return False
    plugins = _parse_json(text).get("plugins")
    if not isinstance(plugins, MutableMapping):
        return False
    entries = plugins.get("entries")
    return isinstance(entries, MutableMapping) and OPENCLAW_PLUGIN_ID in entries


def is_entry_enabled(text: str) -> bool:
    """Whether ``plugins.entries.<id>.enabled`` is present-and-true."""
    if not text.strip():
        return False
    plugins = _parse_json(text).get("plugins")
    if not isinstance(plugins, MutableMapping):
        return False
    entries = plugins.get("entries")
    if not isinstance(entries, MutableMapping):
        return False
    entry = entries.get(OPENCLAW_PLUGIN_ID)
    return isinstance(entry, MutableMapping) and entry.get("enabled") is True


__all__ = [
    "OPENCLAW_ENTRY_FILENAME",
    "OPENCLAW_EXTENSIONS_SUBDIR",
    "OPENCLAW_PLUGIN_ID",
    "apply_entry_enable",
    "apply_entry_remove",
    "has_entry",
    "is_entry_enabled",
    "render_openclaw_extension",
]
