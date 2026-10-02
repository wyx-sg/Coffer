"""What every part of a thin sync round shares: its ports and small helpers."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from coffer.application.sync.round_ports import (
    MachinePort,
    RoundStatePort,
    ScratchPort,
    SyncGitPort,
)
from coffer.application.sync.round_trees import TreeReader
from coffer.application.vault.ports import VaultWriterPort
from coffer.domain.sync.rounds import AppliedChange, PulledCommit
from coffer.domain.vault.history import Commit
from coffer.domain.vault.layout import MACHINES, MANIFEST
from coffer.domain.vault.writers import OP_SYNC, WRITER_SYNC, CommitMeta
from coffer.domain.vault.writes import Validator

_STATUS = {"A": "added", "M": "modified", "D": "removed"}


def now_iso(clock: Callable[[], datetime]) -> str:
    return clock().astimezone(UTC).isoformat(timespec="seconds")


class _HistoryAdapter:
    """The validator's view of history, over the round's git port."""

    def __init__(self, git: SyncGitPort) -> None:
        self._git = git

    def read(self, ref: str, path: str) -> bytes | None:
        return self._git.read(ref, path)

    def tree(self, ref: str = "HEAD", prefix: str = "") -> dict[str, str]:
        return self._git.files(ref, prefix)


@dataclass
class RoundDeps:
    git: SyncGitPort
    state: RoundStatePort
    writer: VaultWriterPort
    machine: MachinePort
    scratch: ScratchPort | None = None
    validate: Validator | None = None
    cloud_folder: Callable[[], str | None] = lambda: None
    #: ``(line, key)`` for each plaintext secret in a file's text — the
    #: detection ``coffer secret scan`` uses. ``None`` reads nothing before a
    #: push (spec vault-sync "Refuse to push a plaintext secret").
    find_plaintext: Callable[[str], Sequence[tuple[int, str]]] | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)
    #: The layout this build writes. A remote above it is a newer Coffer's and
    #: is refused; one below it is replaced by this vault (never converted in
    #: place).
    layout: int = 3
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.trees = TreeReader(self.git)
        self.history = _HistoryAdapter(self.git)

    def now(self) -> str:
        return now_iso(self.clock)

    def sync_meta(self, summary: str) -> CommitMeta:
        return CommitMeta(writer=WRITER_SYNC, operation=OP_SYNC, summary=summary)

    def changes(self, a: str | None, b: str) -> tuple[AppliedChange, ...]:
        """The vault content that differs from ``a`` to ``b`` (the registry and
        the manifest are not content)."""
        return tuple(
            AppliedChange(c.path, _STATUS.get(c.status, "modified"))
            for c in self.git.diff(a, b)
            if not c.path.startswith(MACHINES + "/") and c.path != MANIFEST
        )

    def labels(self, tree: str) -> dict[str, str]:
        files = self.git.files(tree, MACHINES)
        data = self.git.blobs(list(files.values()))
        return self.machine.labels({p: data[b] for p, b in files.items() if b in data})

    def pulled(
        self, local: str | None, remote: str
    ) -> tuple[tuple[PulledCommit, ...], tuple[str, ...]]:
        """The commits ``remote`` brings that ``local`` lacks, and the
        machines that made them."""
        commits: list[Commit] = self.git.commits_between(local, remote)
        labels = self.labels(remote)
        own = self.machine.machine_id()
        out: list[PulledCommit] = []
        machines: list[str] = []
        for c in commits:
            label = labels.get(c.meta.machine or "", c.meta.machine)
            if c.meta.machine and c.meta.machine != own and label and label not in machines:
                machines.append(label)
            out.append(
                PulledCommit(c.version, c.time.isoformat(timespec="seconds"), label, len(c.paths))
            )
        return tuple(out), tuple(machines)

    def layout_of(self, commit: str) -> int | None:
        raw = self.git.read(commit, MANIFEST)
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("utf-8")).get("schema_version")
        except (ValueError, AttributeError):
            return None
        return value if isinstance(value, int) else None


__all__ = ["RoundDeps", "now_iso"]
