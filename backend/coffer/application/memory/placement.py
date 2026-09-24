"""Which partition one raw entry files into — the one place that is decided.

Split out of ``aggregate.py``, which runs the pass; this module is the rule the
pass applies to each entry (spec memory "Identify a partition by its
repository", "File personal entries into global", "Create no partition for a
non-repository directory"). A change to where an entry belongs must bump
``source_state.STATE_VERSION`` so the next pass re-files what an unchanged
source produced.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Sequence
from dataclasses import dataclass

from coffer.domain.memory.note import PERSONAL_TYPES
from coffer.domain.memory.partition import GLOBAL_PARTITION, disambiguate, partition_slug
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory.repository import Repository, resolve_repository


@dataclass(frozen=True)
class Placement:
    """One partition, by the only three things that identify it (see "Identify a
    partition by its repository").

    The same value serves as input and as output: the caller seeds a pass with
    the partitions that already have a Resource row, and the pass hands back
    the ones it filed into — including the repository it resolved, which the
    caller records on the row so a later session's ``cwd`` can be matched
    against it without re-walking a disk. ``global`` is the one placement with
    neither a key nor a path: it is not a repository, and nothing resolves *to*
    it by matching a directory.
    """

    name: str
    repository_key: str = ""
    repository_path: str = ""


GLOBAL_PLACEMENT = Placement(name=GLOBAL_PARTITION)


def home_dir() -> str:
    """The developer's home directory, by the same rule ``paths.py`` uses.

    An entry whose project root IS this directory is about the person, not a
    project, and files into ``global`` whatever its type says (see "File personal entries
    into global").
    """
    return str(pathlib.Path(os.environ.get("HOME", "~")).expanduser()).rstrip("/")


class Placer:
    """Decides which partition one raw entry files into, and names a new one.

    Held across a whole pass rather than recomputed per entry for two reasons.
    The cheap one: resolving a repository walks a directory tree and reads a
    ``.git/config``, and one agent's memory names the same handful of working
    directories hundreds of times. The load-bearing one: a name minted for a
    repository this pass has not seen before must not be minted twice, so the
    set of claimed names has to outlive a single entry.
    """

    def __init__(self, known: Sequence[Placement]) -> None:
        self._by_key = {p.repository_key: p for p in known if p.repository_key}
        self._claimed = {p.name for p in known} | {GLOBAL_PARTITION}
        self._by_directory: dict[str, Placement] = {}
        self._home = home_dir()

    def place(self, entry: RawEntry) -> Placement:
        """Where ``entry`` belongs (see "File personal entries into global" and "Create no
        partition for a non-repository directory").

        Three routes to ``global``, and they are different rules that happen to
        agree: a ``user`` entry (**about the person**, ``PERSONAL_TYPES``) goes
        there whichever repository it was learned in; an entry with no working
        directory has nothing else to say; and an entry learned in a directory
        inside no repository goes there too — into ``global``'s ``.raw/``,
        creating no partition, for the distil pass to keep or discard on its
        merits. A ``feedback`` entry takes no route of its own: learned in a
        repository it files into that repository's partition, and only the
        second and third routes take it to ``global``.

        This method is the one place a raw entry's partition is decided; a
        change to it must bump ``source_state.STATE_VERSION`` so the next pass
        re-reads every source and re-files what an unchanged source produced.
        """
        if entry.type in PERSONAL_TYPES:
            return GLOBAL_PLACEMENT
        directory = (entry.project_root or "").rstrip("/")
        if not directory or directory == self._home:
            return GLOBAL_PLACEMENT
        cached = self._by_directory.get(directory)
        if cached is None:
            cached = self._resolve(directory)
            self._by_directory[directory] = cached
        return cached

    def _resolve(self, directory: str) -> Placement:
        repository = resolve_repository(directory)
        if repository is None or not repository.key:
            return GLOBAL_PLACEMENT
        known = self._by_key.get(repository.key)
        if known is not None:
            return known
        placement = self._mint(repository)
        self._by_key[repository.key] = placement
        self._claimed.add(placement.name)
        return placement

    def _mint(self, repository: Repository) -> Placement:
        """A placement for a repository no partition answers for yet.

        The name is the repository's own, readably — never an id, which is the
        failure that got the previous per-project store removed: nobody could
        tell which project a ``project-<ULID>`` store belonged to. Two
        repositories that share a directory name are told apart by prefixing a
        parent segment (``work-api`` vs ``personal-api``), not by a number.

        Preferring the *remote's* last segment over the local directory's is
        what keeps two clones under different local names from racing to create
        two partitions that ``repository_key`` would then insist are one.
        """
        base = partition_slug(repository.name or repository.root)
        name = (
            disambiguate(repository.root, frozenset(self._claimed))
            if base in self._claimed
            else base
        )
        return Placement(name=name, repository_key=repository.key, repository_path=repository.root)


__all__ = ["GLOBAL_PLACEMENT", "Placement", "Placer", "home_dir"]
