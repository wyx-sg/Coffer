"""Repository identity — what a partition is actually keyed on.

Spec memory "Identify a partition by its repository" and "Create no partition
for a non-repository directory".

A partition used to be keyed on the working directory a fact was learned in.
Measured on the maintainer's live vault, that produced three distinct
failures at once, and all three are one mistake:

* **Split.** A worktree of a repository is a different path, so what an agent
  learned in ``repo/.claude/worktrees/x`` filed away from what it learned in
  ``repo``. The same goes for a second clone.
* **Orphan.** ``blackcat-entry-task`` survived as a partition whose directory
  no longer existed, so nothing could ever resolve to it and its notes were
  delivered to nobody.
* **Impostor.** Six of sixteen partitions were dated scratch folders under
  ``~/Documents/Codex/<date>/<topic>`` — one-off session directories that
  Codex happened to run in. Each got a permanent partition, and what was
  learned there could never reach the repository it was actually about.

A path is not an identity; a **repository** is. This module holds the pure
half of deciding that — normalising a remote URL into a comparable key, and
choosing which key a repository answers to. The filesystem half (finding the
``.git`` above a directory, following a worktree's pointer, reading the
remote out of a config file) is infrastructure's, in
:mod:`coffer.infrastructure.memory.repository`.

Two clones of one upstream are the same repository, so the **remote URL wins
when there is one**; a repository with no remote at all can only be itself,
so it falls back to its own path. The two are kept apart by a prefix so a
path can never collide with a URL.
"""

from __future__ import annotations

import re

#: A repository identified by its upstream: two clones share this key.
SCHEME_REMOTE = "remote"
#: A repository with no upstream, identified by where it lives.
SCHEME_PATH = "path"

_SCP_LIKE = re.compile(r"^(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>.+)$")
_URL_LIKE = re.compile(
    r"^[A-Za-z][A-Za-z0-9+.\-]*://(?:[^@/]+@)?(?P<host>[^/:]+)(?::\d+)?/(?P<path>.+)$"
)


def normalise_remote(url: str) -> str:
    """A comparable key for a git remote URL, or ``""`` when it is not one.

    Two clones of one repository are routinely configured with different
    spellings of the same upstream — ``git@host:owner/repo.git`` and
    ``https://host/owner/repo`` are the common pair, and ``ssh://git@host/``
    is a third. Comparing them literally would file them apart, which is the
    failure this whole module exists to avoid, so the scheme, any user, any
    port, a trailing ``.git`` and a trailing slash are all dropped and the
    host is lowercased. The *path* keeps its case: ``owner/Repo`` and
    ``owner/repo`` are distinct on most forges, and folding them would file
    two real repositories together — the opposite error, and a worse one.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    match = _URL_LIKE.match(raw) or _SCP_LIKE.match(raw)
    if match is None:
        return ""
    host = match.group("host").lower()
    path = match.group("path").strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    if not host or not path:
        return ""
    return f"{host}/{path}"


def repository_key(*, remote_url: str, root_path: str) -> str:
    """The identity a repository answers to.

    ``remote_url`` wins when it normalises, so a second clone and a worktree
    land in one partition. A repository with no usable remote falls back to
    its own root path, which is the only thing that can distinguish it.
    Returns ``""`` when neither is usable — the caller is not looking at a
    repository, and "Create no partition for a non-repository directory" says
    that gets no partition.
    """
    remote = normalise_remote(remote_url)
    if remote:
        return f"{SCHEME_REMOTE}:{remote}"
    root = (root_path or "").rstrip("/")
    if root:
        return f"{SCHEME_PATH}:{root}"
    return ""


def repository_name(*, remote_url: str, root_path: str) -> str:
    """The readable name a partition derived from this repository should use.

    The repository's own last path segment — what the developer calls it —
    preferring the remote's, so two clones under different local directory
    names still agree on one name rather than racing to create two partitions
    that :func:`repository_key` would then insist are one.
    """
    remote = normalise_remote(remote_url)
    source = remote or (root_path or "").rstrip("/")
    return source.rsplit("/", 1)[-1] if source else ""


__all__ = [
    "SCHEME_PATH",
    "SCHEME_REMOTE",
    "normalise_remote",
    "repository_key",
    "repository_name",
]
