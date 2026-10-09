"""Write: the hub into this machine's agents (spec memory "Write the hub into
Claude Code's native memory", "Write the hub into Codex's memory extension").

For each registered agent here whose writer can write, every hub entry is a
target except:

- one that came from this agent on this machine ("Never write a memory back
  into the agent and machine it came from");
- a project's entry while the project is not checked out here ("Write a
  project's memories only where it is checked out");
- a Claude Code entry for Codex while Codex imports Claude Code's memories
  itself ("Defer to Codex's own import from Claude Code").

The copies are planned against the ledger by
:func:`coffer.domain.memory.sync_plan.plan_copies` and applied here, each
re-checked against the disk first: a copy is only ever rewritten or removed
while it is still exactly what Coffer wrote.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from coffer.domain.memory import absorption
from coffer.domain.memory.hub import CLAUDE_CODE, CODEX, HubEntry
from coffer.domain.memory.native_writer import AuxWrite, NativeWriter
from coffer.domain.memory.portable import from_portable
from coffer.domain.memory.sync_plan import (
    ACTION_REMOVE,
    ACTION_WRITE,
    STATE_WRITTEN,
    AgentPlan,
    CopyOp,
    CopyRecord,
    Target,
    digest_text,
    plan_copies,
)
from coffer.infrastructure.memory import native_files
from coffer.infrastructure.memory.sync_ledger import Ledger
from coffer.infrastructure.memory.writers.codex import extension_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalAgent:
    """A registered agent on this machine, as the writer needs it."""

    agent: str
    agent_type: str
    config_dir: str

    @property
    def key(self) -> str:
        """What the ledger files this agent's copies under: two agents of one
        type (two Claude Code config directories) keep apart."""
        return f"{self.agent_type}@{self.config_dir}"


@dataclass
class AgentTargets:
    copies: list[Target] = field(default_factory=list)
    globals: list[Target] = field(default_factory=list)
    #: Project entries held back because the project is not checked out here.
    held_back: int = 0

    def by_entry(self) -> dict[str, Target]:
        return {t.entry.id: t for t in [*self.copies, *self.globals]}


def targets_for(
    agent_type: str,
    writer: NativeWriter,
    hub: Mapping[str, HubEntry],
    *,
    machine: str,
    checkouts: Mapping[str, str],
    home: str,
    codex_imports_claude: bool,
) -> AgentTargets:
    out = AgentTargets()
    for entry in sorted(hub.values(), key=lambda e: e.id):
        if entry.origin.machine == machine and entry.origin.agent == agent_type:
            continue
        if agent_type == CODEX and entry.origin.agent == CLAUDE_CODE and codex_imports_claude:
            continue
        root: str | None = None
        if entry.project:
            root = checkouts.get(entry.project)
            if root is None:
                out.held_back += 1
                continue
        target = Target(
            entry=entry, root=root, body=from_portable(entry.body, repo_root=root, home=home)
        )
        if writer.wants(target):
            out.copies.append(target)
        else:
            out.globals.append(target)
    return out


def plan_agent(
    writer: NativeWriter, local: LocalAgent, targets: AgentTargets, ledger: Ledger
) -> AgentPlan:
    return plan_copies(
        local.agent_type,
        targets.copies,
        ledger.agent_copies(local.key),
        path_for=lambda target, taken: writer.path_for(local.config_dir, target, taken),
        render=writer.render,
        digest_of=native_files.digest,
    )


@dataclass
class Applied:
    written: list[CopyOp] = field(default_factory=list)
    updated: list[CopyOp] = field(default_factory=list)
    removed: list[CopyOp] = field(default_factory=list)
    #: Coffer's own files beside the copies that changed (block, rules, instructions).
    aux: list[str] = field(default_factory=list)
    skipped: list[CopyOp] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.written or self.updated or self.removed or self.aux)


def apply_ops(
    writer: NativeWriter,
    local: LocalAgent,
    ops: Sequence[CopyOp],
    targets: AgentTargets,
    plan_records: Mapping[str, CopyRecord],
    ledger: Ledger,
) -> Applied:
    """Apply ``ops`` for one agent, each re-checked against the disk, then
    rewrite Coffer's own files beside them. Records each in ``ledger``."""
    done = Applied()
    before = dict(ledger.agent_copies(local.key))
    # The plan's view of the copies (each one's state observed on disk)
    # replaces the ledger's: a copy the plan no longer tracks is forgotten.
    copies = ledger.copies[local.key] = dict(plan_records)
    for op in ops:
        path = pathlib.Path(op.path)
        rec = copies.get(op.path) or before.get(op.path)
        current = native_files.digest(path)
        if op.action == ACTION_WRITE:
            if current is not None and not (
                rec and rec.state == STATE_WRITTEN and rec.digest == current
            ):
                done.skipped.append(op)
                continue
        elif rec is None or rec.state != STATE_WRITTEN or current != rec.digest:
            done.skipped.append(op)
            continue
        if op.action == ACTION_REMOVE:
            native_files.remove(path)
            copies.pop(op.path, None)
            done.removed.append(op)
            continue
        native_files.write(path, op.content)
        copies[op.path] = CopyRecord(
            op.path, op.entry, op.entry_updated_at, digest_text(op.content), STATE_WRITTEN
        )
        ledger.deliver(local.agent_type, absorption.fingerprints(op.content))
        (done.written if op.action == ACTION_WRITE else done.updated).append(op)
    for aux in writer.aux(local.config_dir, copies, targets.by_entry(), targets.globals):
        if _apply_aux(aux):
            done.aux.append(aux.path)
    for target in targets.globals:
        ledger.deliver(local.agent_type, absorption.fingerprints(target.body))
    return done


def _apply_aux(aux: AuxWrite) -> bool:
    path = pathlib.Path(aux.path)
    current = native_files.read(path)
    if aux.content == current:
        return False
    if aux.backup and current is not None:
        native_files.backup(path)
    if aux.content is None:
        return native_files.remove(path)
    native_files.write(path, aux.content)
    return True


def undo_agent(writer: NativeWriter, local: LocalAgent, ledger: Ledger) -> Applied:
    """Remove every copy Coffer wrote into one agent that is still as written,
    and Coffer's own files beside them. Edited copies stay; the ledger forgets
    every copy of this agent."""
    done = Applied()
    copies = ledger.agent_copies(local.key)
    for path, rec in sorted(copies.items()):
        if rec.state == STATE_WRITTEN and native_files.digest(path) == rec.digest:
            native_files.remove(pathlib.Path(path))
            done.removed.append(
                CopyOp(
                    local.agent_type, ACTION_REMOVE, path, rec.entry, rec.entry_updated_at, "", ""
                )
            )
    for aux in writer.undo(local.config_dir, copies):
        if _apply_aux(aux):
            done.aux.append(aux.path)
    _prune_empty(writer, local)
    ledger.copies[local.key] = {}
    return done


def _prune_empty(writer: NativeWriter, local: LocalAgent) -> None:
    """Remove Codex's extension folders Coffer made, once they are empty."""
    if local.agent_type != CODEX:
        return
    folder = extension_dir(local.config_dir)
    for d in (folder / "resources", folder):
        with contextlib.suppress(OSError):
            d.rmdir()


__all__ = [
    "AgentTargets",
    "Applied",
    "LocalAgent",
    "apply_ops",
    "plan_agent",
    "targets_for",
    "undo_agent",
]
