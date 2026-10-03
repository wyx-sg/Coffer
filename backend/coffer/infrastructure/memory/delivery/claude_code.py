"""Claude Code's memory hook adapter.

Coffer installs one entry on each of two events in `~/.claude/settings.json`
(the allowlisted `"settings"` key — `domain.agent.allowlists._claude_code_files`),
the same file a developer's own `env`, `permissions` and hand-wired hooks live
in: `SessionStart` (matched on every source that starts a session —
`startup|resume|clear|compact`) and `UserPromptSubmit`. Both entries run the
same `coffer memory hook` command, which reads the event from stdin and prints
the event's JSON `hookSpecificOutput` (`domain.memory.hook_output`).

Claude Code keeps a hook's output inline up to about 10,000 characters; the
session-start payload is bounded under that
(`domain.memory.delivery.DELIVERY_CEILING_BYTES`). Claude Code runs every hook
in its settings; there is no trust step, so `trust` always answers
`NOT_REQUIRED`. The CLI is still called by absolute path: Claude Code started
from the Dock or an IDE does not inherit the login shell's `PATH`.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.hook_trust import HookTrust
from coffer.domain.memory import delivery

EVENT = delivery.events_label(delivery.DELIVERY_EVENTS)
CONFIG_KEY = "settings"


@dataclass(frozen=True)
class ClaudeCodeDelivery:
    """`domain.memory.delivery.DeliveryAdapter` for Claude Code."""

    #: The agent this adapter serves, by its type value (the memory kind
    #: declares it as a value; it may not import the agent kind's modules).
    agent_type: str = "claude_code"
    config_key: str = CONFIG_KEY
    event: str = EVENT
    #: The `coffer` CLI the hook runs — an absolute path, resolved by the
    #: composition root (see `domain.memory.delivery.hook_invocation`).
    cli: str = "coffer"
    trust_config_key: str | None = None

    def command_for(self, agent_uid: str) -> str:
        return delivery.entry_command(agent_uid, cli=self.cli)

    def install(self, text: str, agent_uid: str) -> str:
        return delivery.install_entries(text, delivery.delivery_entries(agent_uid, cli=self.cli))

    def remove(self, text: str) -> str:
        return delivery.remove_entry(text)

    def find_command(self, text: str) -> str | None:
        return delivery.find_command(text)

    def find(self, text: str) -> delivery.InstalledHook | None:
        return delivery.find_installed(text)

    def find_all(self, text: str) -> list[delivery.InstalledHook]:
        return delivery.find_all_installed(text)

    def is_coffer_command(self, command: str) -> bool:
        return delivery.is_marked(command)

    def trust(self, hooks_text: str, trust_text: str | None, hooks_path: str) -> HookTrust:
        del hooks_text, trust_text, hooks_path
        return HookTrust.NOT_REQUIRED


ADAPTER = ClaudeCodeDelivery()
