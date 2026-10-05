"""The chore of bringing an earlier version of a vault file back, handed to the
person's agent (spec vault-storage "Hand restoring an earlier version of a
vault file to an agent").

Coffer does not list, diff or restore versions: the vault is a git repository
and its history is git's. The prompt tells an agent how to do the restore so
the commit it makes names its writer like every other vault commit (ADR
every-vault-write-is-a-validated-commit-naming-its-writer). A prompt carries
no secret: a path under ``secret/`` never gets one.
"""

from __future__ import annotations

import shlex
from datetime import datetime

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.vault.errors import VaultPathRefused
from coffer.domain.vault.layout import SECRET
from coffer.domain.vault.writers import (
    OP_RESTORE,
    TRAILERS,
    WRITER_AGENT,
)
from coffer.domain.vault.writes import check_path


def history_spec(path: str) -> str:
    """``path`` as a vault-relative file, or a folder ending in ``/``; refuse
    anything outside the vault and everything under ``secret/`` (rolling a
    secret back is re-entering it, never an agent's chore)."""
    folder = path.endswith("/")
    clean = check_path(path.rstrip("/"))
    if clean == SECRET or clean.startswith(f"{SECRET}/"):
        raise VaultPathRefused(f"{SECRET}/ is not read or restored through history")
    return clean + "/" if folder else clean


def log_command(vault: str, spec: str) -> str:
    """The command that prints the history of ``spec`` with its changes."""
    return f"git -C {shlex.quote(vault)} log -p -- {shlex.quote(spec.rstrip('/') or '.')}"


def restore_handoff(vault: str, spec: str, at: datetime | None = None) -> str:
    """The prompt asking an agent to restore ``spec`` (see :func:`history_spec`)."""
    folder = spec.endswith("/")
    kind = "folder" if folder else "file"
    when = (
        f"how it was at {at.isoformat()}"
        if at is not None
        else "an earlier version that I will choose"
    )
    trailers = (
        f"{TRAILERS['writer']}: {WRITER_AGENT}",
        f"{TRAILERS['operation']}: {OP_RESTORE}",
        f"{TRAILERS['restored_from']}: <the commit you restored from>",
    )
    facts = [
        f"The {kind} is {spec}, relative to the vault.",
        f"The vault is a git repository at {vault}.",
        f"Its history is printed by: {log_command(vault, spec)}",
        "History is never rewritten: no reset, amend, rebase or force push.",
    ]
    steps = [
        (
            f"Find the commit that left the {kind} as it was at {at.isoformat()} "
            f"and bring the {kind} back to that."
            if at is not None
            else f"List the {kind}'s recent versions from the log, ask me which one to bring "
            "back, and wait for my answer."
        ),
        (
            f"Write that version's content back into the working tree, touching only {spec}"
            + (", and remove the files inside it that version did not have." if folder else ".")
        ),
        "Make one new commit of that change, and end its message with a blank line and these "
        "three trailer lines:\n" + "\n".join(trailers),
        "Tell me what you restored, from which commit.",
    ]
    return render_handoff(
        Handoff(
            task=f"Restore {spec} in my Coffer vault to {when}.",
            facts=tuple(facts),
            steps=tuple(steps),
        )
    )


__all__ = ["history_spec", "log_command", "restore_handoff"]
