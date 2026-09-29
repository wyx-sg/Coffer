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

The hook prints the index as plain stdout, which Claude Code adds to the
session's context whole up to about 10,000 characters (the payload is bounded
under that, `domain.memory.delivery.DELIVERY_CEILING_BYTES`). Claude Code runs
every hook in its settings; there is no trust step, so `trust` always answers
`NOT_REQUIRED`. The CLI is still called by absolute path: Claude Code started
from the Dock or an IDE does not inherit the login shell's `PATH`.
"""

from __future__ import annotations

from dataclasses import dataclass

from coffer.domain.hook_trust import HookTrust
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

    #: The agent this adapter serves, by its type value (the memory kind
    #: declares it as a value; it may not import the agent kind's modules).
    agent_type: str = "claude_code"
    config_key: str = CONFIG_KEY
    event: str = EVENT
    #: The `coffer` CLI the hook runs — an absolute path, resolved by the
    #: composition root (see `domain.memory.delivery.context_invocation`).
    cli: str = "coffer"
    trust_config_key: str | None = None

    def command_for(self, agent_uid: str) -> str:
        return delivery.hook_command(agent_uid, cli=self.cli)

    def install(self, text: str, agent_uid: str) -> str:
        return delivery.install_entry(
            text,
            event=self.event,
            command=self.command_for(agent_uid),
            matcher=MATCHER,
            timeout=TIMEOUT_SECONDS,
        )

    def remove(self, text: str) -> str:
        return delivery.remove_entry(text)

    def find_command(self, text: str) -> str | None:
        return delivery.find_command(text)

    def find(self, text: str) -> delivery.InstalledHook | None:
        return delivery.find_installed(text)

    def is_coffer_command(self, command: str) -> bool:
        return delivery.is_marked(command)

    def trust(self, hooks_text: str, trust_text: str | None, hooks_path: str) -> HookTrust:
        del hooks_text, trust_text, hooks_path
        return HookTrust.NOT_REQUIRED


ADAPTER = ClaudeCodeDelivery()
