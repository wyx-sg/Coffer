"""Render Coffer's session-context plugin file for a PLUGIN_DROP agent.

Pure domain text rendering — no filesystem access — the third
:class:`~coffer.domain.agent.context_injection.InjectionMode` (ADR-042). An
agent with no shell hook but an in-process JS/TS plugin API (opencode) gets a
thin plugin file dropped into its auto-loaded plugin directory
(``~/.config/opencode/plugin/`` — probe-verified on opencode 1.14.48). The
plugin spawns the same ``coffer-hook`` binary the shell-command agents exec
(``--dialect raw`` prints the plain-text FR-044 bundle) and pushes its stdout
onto the system prompt via ``experimental.chat.system.transform``.

Unlike ``INSTRUCTIONS_BLOCK`` this mode is *dynamic*: the plugin fetches the
bundle live (cached per session), so no pre-turn refresh machinery exists for
it. The dropped file is recognised by its fixed name — Coffer owns everything
about ``coffer-session-context.js``; uninstall deletes the file.

The hook binary path and agent name are embedded via ``json.dumps``, which
produces valid JS string literals for any path (spaces, quotes, non-ASCII) —
and the plugin spawns argv directly (no shell), so no further quoting exists
to get wrong.
"""

from __future__ import annotations

import json

#: The dropped plugin's filename — Coffer's namespace claim inside the agent's
#: plugin directory. Presence of this file == "installed".
PLUGIN_FILENAME = "coffer-session-context.js"

#: Subdirectory of the agent's config dir that its runtime auto-loads plugin
#: modules from.
PLUGIN_SUBDIR = "plugin"

_TEMPLATE = """\
// coffer:session-context — managed by Coffer; do not edit (overwritten on
// reinstall). Remove via the Coffer agent page or `coffer agent hook uninstall`.
// Injects Coffer's rules + memory bundle into every session's system prompt by
// spawning the same coffer-hook binary the shell-hook agents exec.
import {{ spawn }} from "node:child_process";

const HOOK = {hook};
const AGENT = {agent};
const TIMEOUT_MS = 5000;
const cache = new Map();

function fetchContext() {{
  return new Promise((resolve) => {{
    let out = "";
    let child;
    try {{
      child = spawn(HOOK, ["--agent", AGENT, "--dialect", "raw", "--event", "sessionStart"], {{
        stdio: ["ignore", "pipe", "ignore"],
        timeout: TIMEOUT_MS,
      }});
    }} catch {{
      resolve("");
      return;
    }}
    child.stdout.on("data", (d) => {{ out += d; }});
    child.on("error", () => resolve(""));
    child.on("close", (code) => resolve(code === 0 ? out.trim() : ""));
  }});
}}

export const CofferSessionContext = async () => ({{
  "experimental.chat.system.transform": async (input, output) => {{
    // FAILURE-IS-SILENT: a broken daemon must never break the user's agent.
    try {{
      const key = (input && input.sessionID) || "global";
      let ctx = cache.get(key);
      if (ctx === undefined) {{
        ctx = await fetchContext();
        cache.set(key, ctx);
      }}
      if (ctx) output.system.push(ctx);
    }} catch {{}}
  }},
}});
"""


def render_plugin(*, hook_binary: str, agent_name: str) -> str:
    """The plugin file's full text for one agent."""
    return _TEMPLATE.format(hook=json.dumps(hook_binary), agent=json.dumps(agent_name))
