"""Which repository a directory belongs to, read off the disk.

See spec memory "Identify a partition by its repository" and "Create no
partition for a non-repository directory".

:mod:`coffer.domain.memory.repository` decides what a repository's *identity*
is once you know its root and its remote. This module is the half that has to
touch a filesystem to find those two things, and it exists as its own file for
the reason the layering rule gives: the domain stays pure, so the walk up
through ``.git`` markers lives here.

It resolves three shapes to one answer, which is the whole point:

* **An ordinary checkout.** ``.git`` is a directory; its parent is the root.
* **A worktree.** ``.git`` is a *file* holding ``gitdir: <abs path>``, pointing
  at a private directory under the main checkout's ``.git/worktrees/<name>``.
  That directory holds a ``commondir`` file — usually ``../..`` — naming the
  main ``.git``, and *that* directory's parent is the root. Following the
  pointer is what makes this repository's own development worktrees (which sit
  under ``.claude/worktrees/``) file into the same partition as the main
  checkout instead of one partition per branch in flight.
* **A second clone.** A different root entirely, but the same ``origin`` URL,
  which :func:`coffer.domain.memory.repository.repository_key` prefers over the
  path for exactly this case.

The remote is read by parsing ``.git/config`` rather than by shelling out to
``git``. Three reasons, in order of how much they cost when ignored: a
subprocess per aggregated source turns a pass that touches a few hundred files
into a few hundred process spawns; ``git`` need not be installed, or need not
be the ``git`` on this ``$PATH``, on a machine whose agents Coffer is reading;
and a subprocess inherits an environment a caller can influence, where reading
a file cannot be made to do anything but read a file.

**Nothing here raises for a broken repository.** A ``gitdir:`` pointing at a
directory that was deleted, a ``commondir`` climbing past the filesystem root, a
``config`` that is unreadable or is not UTF-8 — each is an ordinary state of a
developer's disk, not an error in Coffer, and "Create no partition for a
non-repository directory" already says that *not being in a repository* is a
normal answer with a normal consequence (no partition). A pass that crashed on
one of them would stop aggregating every other agent's memory over a stale
pointer in a directory nobody has opened in a year.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

from coffer.domain.memory.repository import repository_key, repository_name

#: The marker every git checkout has at its root: a directory in an ordinary
#: clone, a file in a worktree.
GIT_MARKER = ".git"
#: Prefix of the one line a worktree's ``.git`` file holds.
GITDIR_PREFIX = "gitdir:"
#: File inside a worktree's private git directory naming the main ``.git``.
COMMONDIR_NAME = "commondir"
#: The config file the ``origin`` remote is read out of.
CONFIG_NAME = "config"

#: How far up the tree the walk will climb before giving up. A repository root
#: is a handful of levels above any file in it; a cap this size is unreachable
#: in practice and bounds the walk for a path that resolution turned into
#: something pathological.
MAX_WALK_DEPTH = 64


@dataclass(frozen=True)
class Repository:
    """One repository on this disk, as much of it as partitioning needs.

    Two fields, because the domain's identity rule reads exactly two: the
    absolute root — which "Identify a partition by its repository" also requires
    be recorded on the partition's Resource and restated in its ``MEMORY.md`` —
    and the ``origin`` URL, which is ``""`` when the repository has no remote at
    all. A repository with no remote is not a degraded case; it can only ever be
    itself, and the domain falls back to its path for exactly that reason.
    """

    #: Absolute path of the repository root — the main checkout's, even when
    #: the directory that was resolved was a worktree of it.
    root: str
    #: The ``origin`` remote's URL, or ``""`` when there is none to read.
    remote_url: str = ""

    @property
    def key(self) -> str:
        """The identity this repository answers to (domain's rule, not ours)."""
        return repository_key(remote_url=self.remote_url, root_path=self.root)

    @property
    def name(self) -> str:
        """The readable name a partition derived from this should carry."""
        return repository_name(remote_url=self.remote_url, root_path=self.root)


def resolve_repository(directory: str | pathlib.Path) -> Repository | None:
    """The repository ``directory`` is inside, or ``None`` when it is in none.

    ``None`` is the answer "Create no partition for a non-repository directory"
    is about, and it is not an error: a dated scratch folder a session happened
    to run in gets no partition, and its entries are held for the distil pass to
    judge on their merits. The previous design keyed partitions on the raw
    working directory and turned six such folders on the maintainer's machine
    into six permanent partitions whose contents could never reach the project
    they were actually about.

    The path is resolved before the walk, so a symlinked checkout and its real
    location agree on one answer rather than producing two partitions for one
    repository. It is resolved non-strictly, because a directory an agent
    recorded months ago may no longer exist — in which case the walk simply
    finds no marker above it and the answer is ``None``, which is what "Report
    unresolvable partitions" then reports as unresolvable rather than delivering
    to nobody.
    """
    try:
        start = pathlib.Path(directory).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None
    if not str(start).startswith("/"):
        return None

    for candidate in (start, *start.parents)[:MAX_WALK_DEPTH]:
        git_dir = _git_dir_at(candidate)
        if git_dir is None:
            continue
        root = git_dir.parent
        if not _is_plausible_root(root):
            # The marker exists but points somewhere that cannot be a checkout.
            # Keep climbing: an outer repository may still legitimately claim
            # this directory, and a broken inner pointer must not hide it.
            continue
        return Repository(root=str(root), remote_url=read_origin_url(git_dir))
    return None


def _git_dir_at(candidate: pathlib.Path) -> pathlib.Path | None:
    """The *common* git directory for a checkout rooted at ``candidate``.

    "Common" is the load-bearing word: for a worktree this deliberately returns
    the **main** checkout's ``.git``, never the worktree's own private
    directory, because the main checkout's is what both of them share and
    therefore the only thing they can agree an identity on.
    """
    marker = candidate / GIT_MARKER
    try:
        if marker.is_dir():
            return marker
        if not marker.is_file():
            return None
        text = marker.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return _follow_worktree_pointer(candidate, text)


def _follow_worktree_pointer(candidate: pathlib.Path, text: str) -> pathlib.Path | None:
    """Resolve ``gitdir: …`` plus its ``commondir`` to the main ``.git``.

    Both hops are resolved against the directory that named them — ``gitdir:``
    against the worktree root that holds the ``.git`` file, ``commondir``
    against the private git directory that holds it — because git writes both
    relative in the ordinary case (``../..`` is what ``commondir`` almost
    always says) and absolute when the worktree was created with an absolute
    path. Anything that does not land on a real directory returns ``None``, and
    the caller keeps climbing rather than treating a stale pointer as a
    repository that no longer exists.
    """
    pointer = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(GITDIR_PREFIX):
            pointer = stripped[len(GITDIR_PREFIX) :].strip()
            break
    if not pointer:
        return None

    private = _resolve_against(candidate, pointer)
    if private is None or not private.is_dir():
        return None

    try:
        common_ref = (private / COMMONDIR_NAME).read_text(encoding="utf-8", errors="replace")
    except OSError:
        # No ``commondir`` at all is the shape of a linked checkout that is not
        # a worktree — a submodule's ``.git`` file points straight at its own
        # git directory. Its parent is then the right root, so use it directly.
        return private if _is_plausible_root(private.parent) else None

    common = _resolve_against(private, common_ref.strip())
    if common is None or not common.is_dir():
        return None
    return common


def _resolve_against(base: pathlib.Path, value: str) -> pathlib.Path | None:
    """Join ``value`` onto ``base`` unless it is already absolute; resolve it."""
    if not value:
        return None
    try:
        raw = pathlib.Path(value)
        joined = raw if raw.is_absolute() else base / raw
        return joined.resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return None


def _is_plausible_root(root: pathlib.Path) -> bool:
    """Refuse a "root" that is the filesystem root or is not a directory.

    A ``commondir`` of ``../../../../..`` that climbs out of everything
    resolves to ``/``, and ``/`` as a partition's repository root would name
    the whole machine as one project. It is cheaper to refuse it here than to
    explain later why a partition called ``global`` appeared twice.
    """
    try:
        return root.parent != root and root.is_dir()
    except OSError:
        return False


def read_origin_url(git_dir: pathlib.Path) -> str:
    """The ``origin`` remote's URL from ``git_dir/config``, or ``""``.

    Hand-parsed rather than handed to :mod:`configparser`, which cannot read
    this file: git indents its keys with a tab, and configparser reads an
    indented line as a continuation of the previous value, so every key in a
    real ``.git/config`` would be swallowed into the one above it.

    The first ``url`` in the first ``[remote "origin"]`` section wins, which is
    what ``git remote get-url origin`` answers — a remote may carry several
    URLs, and the extra ones are push mirrors, not a second identity.

    Returns ``""`` for a missing, unreadable, or remote-less config. That is
    not a failure: the domain's key falls back to the root path, and a
    repository with no upstream is correctly filed as only ever being itself.
    """
    try:
        text = (git_dir / CONFIG_NAME).read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""

    in_origin = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#;":
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_origin = _is_origin_section(stripped[1:-1].strip())
            continue
        if not in_origin:
            continue
        key, sep, value = stripped.partition("=")
        if sep and key.strip().lower() == "url":
            return value.strip()
    return ""


def _is_origin_section(header: str) -> bool:
    """Is this section header ``[remote "origin"]``, in either spelling?

    Git accepts the quoted subsection form and the older dotted one
    (``[remote.origin]``). The section name is case-insensitive in both; the
    quoted subsection is case-*sensitive*, so ``[remote "Origin"]`` is a
    different remote and is deliberately not matched, while the dotted form's
    subsection is case-insensitive and is.
    """
    if '"' in header:
        name, _, rest = header.partition('"')
        subsection = rest.rsplit('"', 1)[0]
        return name.strip().lower() == "remote" and subsection == "origin"
    name, _, subsection = header.partition(".")
    return name.strip().lower() == "remote" and subsection.strip().lower() == "origin"


__all__ = [
    "COMMONDIR_NAME",
    "CONFIG_NAME",
    "GITDIR_PREFIX",
    "GIT_MARKER",
    "MAX_WALK_DEPTH",
    "Repository",
    "read_origin_url",
    "resolve_repository",
]
