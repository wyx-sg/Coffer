"""The upgrade's one vault commit, staged without the per-file compare.

Every ordinary vault write goes through the writer's transaction, which reads
each touched path back from ``HEAD`` to compare and validate it — one git
process per path, right for an edit of a few files and far too slow for a
commit of a whole vault. The upgrade has no one to race: the daemon is
stopped, and the vault it writes did not exist a moment ago. So its files are
written here the way the transaction writes them (a new file must be absent,
a sibling temp file renamed into place) and committed with the repository's
own staging primitives, one ``git add`` per two hundred paths.
"""

from __future__ import annotations

from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.writers import CommitMeta
from coffer.domain.vault.writes import Expect, check_path
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.repository import VaultRepository


class LayoutCommit:
    """The paths of the layout commit, written as a transaction writes them."""

    def __init__(self, repo: VaultRepository) -> None:
        self.repo = repo
        self.paths: list[str] = []

    def write(self, path: str, data: bytes, expected: str | Expect | None = Expect.HEAD) -> None:
        path = check_path(path)
        target = self.repo.root / path
        if expected is Expect.ABSENT and target.exists():
            raise VaultFileStale(path, f"{path} already exists")
        atomic_write(target, data)
        if path not in self.paths:
            self.paths.append(path)

    def commit(self, meta: CommitMeta) -> str | None:
        """Stage what was written and everything else that differs from
        ``HEAD`` (the moved trees, the stripped documents) as one commit."""
        changed = [p for _code, p in self.repo.status() if not p.endswith("/")]
        wanted = list(dict.fromkeys([*self.paths, *changed]))
        self.repo.stage(wanted)
        return self.repo.commit_staged(meta)


__all__ = ["LayoutCommit"]
