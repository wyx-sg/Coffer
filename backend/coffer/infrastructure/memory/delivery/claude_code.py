"""Claude Code's session-start hook adapter.

Claude Code's own `hooks.SessionStart` matcher vocabulary is a `|`-joined set
of the *sources* that start a session: a fresh launch (`startup`), `/resume`,
`/clear`, and an auto-`compact`. Coffer installs against all four so its
context lands however the session began — the same choice the removed
injection layer made (see `git show 22dfcc3a^:.../hook_install.py`).

Lives in `~/.claude/settings.json` (the allowlisted `"settings"` key —
`domain.agent.allowlists._claude_code_files`), the same file a developer's
own `env`, `permissions`, and any hand-wired hooks (e.g. skynet-cli's
`UserPromptSubmit`/`PreToolUse`/`Stop` entries) already live in.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.memory import delivery

EVENT = "SessionStart"
CONFIG_KEY = "settings"
MATCHER = "startup|resume|clear|compact"
#: Generous enough that a slow first `coffer memory context` call never
#: blocks the session from starting; short enough a hung daemon doesn't hang
#: the terminal either. Not part of the marker — a future retune is not a
#: reinstall.
TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ClaudeCodeDelivery:
    """`domain.memory.delivery.DeliveryAdapter` for Claude Code."""

    config_key: str = CONFIG_KEY
    event: str = EVENT

    def command_for(self, agent_key: str) -> str:
        return delivery.hook_command(agent_key)

    def install(self, text: str, agent_key: str) -> str:
        return delivery.install_entry(
            text,
            event=self.event,
            command=self.command_for(agent_key),
            matcher=MATCHER,
            timeout=TIMEOUT_SECONDS,
        )

    def remove(self, text: str) -> str:
        return delivery.remove_entry(text, event=self.event)

    def find_command(self, text: str) -> str | None:
        return delivery.find_command(text, event=self.event)


ADAPTER = ClaudeCodeDelivery()
