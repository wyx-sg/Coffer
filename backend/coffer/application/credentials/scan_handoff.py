"""The hand-off for skills that still read keys from ``~/.coffer/secrets/``.

Spec credentials "Move plaintext secret files into the store". Moving a
secrets file's values into the store does not rewrite the skills that read
that file: each command has to get its value from Coffer instead, through
``coffer run``. That rewrite depends on each script, so it is handed to the
person's agent rather than done by Coffer.

The prompt carries only where each mention is (skill, file, line, the path it
names) and the names the secrets file's keys become — never a value, and it
tells the agent not to read one either.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from coffer.domain.handoff import Handoff, render_handoff


class SkillMention(Protocol):
    @property
    def skill(self) -> str: ...
    @property
    def path(self) -> str: ...
    @property
    def line(self) -> int: ...
    @property
    def mention(self) -> str: ...


class SecretsFileKey(Protocol):
    """A key in a ``~/.coffer/secrets/`` file and the secret name it becomes."""

    @property
    def path(self) -> str: ...
    @property
    def key(self) -> str: ...
    @property
    def proposed_name(self) -> str: ...


def mentions_handoff(
    mentions: Sequence[SkillMention], keys: Sequence[SecretsFileKey]
) -> str | None:
    """The prompt to rewrite every mention, or ``None`` when there is none."""
    if not mentions:
        return None
    facts = [f"{m.skill}: {m.path}:{m.line} reads {m.mention}" for m in mentions]
    facts += [
        f"{k.path} key {k.key} becomes the secret {k.proposed_name} "
        f"(coffer://secret/{k.proposed_name}) once I move it into Coffer"
        for k in keys
    ]
    facts += [
        "`coffer run --secret ENV=NAME -- <command>` runs a command with secret NAME in the "
        "variable ENV, set for that command only; `coffer run --env-file <file> -- <command>` "
        "does the same for a KEY=VALUE file whose values are coffer://secret/<name> references.",
        "`coffer credentials list` lists the secret names Coffer holds, never their values.",
    ]
    return render_handoff(
        Handoff(
            task=(
                "These skills read keys from files in ~/.coffer/secrets/. Rewrite each so its "
                "command gets the value from Coffer instead, and never print a value."
            ),
            facts=tuple(facts),
            steps=(
                "At each line above, change the command that reads the file under "
                "~/.coffer/secrets/ to run through `coffer run --secret …` (or `coffer run "
                "--env-file` with coffer://secret/<name> references); leave the rest of the file "
                "as it is.",
                "Never print, echo, log or copy a secret's value, and do not open the files under "
                "~/.coffer/secrets/ to read one; use only the names above.",
                "If a command needs a key that is not a secret in Coffer yet, tell me; I move it "
                "with Find plaintext keys first.",
                "Show me the diff of every file you changed.",
            ),
        )
    )


__all__ = ["SecretsFileKey", "SkillMention", "mentions_handoff"]
