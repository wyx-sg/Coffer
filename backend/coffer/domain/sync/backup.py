"""The sync remote: the one user-owned git repository this vault converges with.

Spec vault-sync "Allow at most one user-owned sync remote"; the user-owned
sync remote exception to Principle I in
``docs-site/architecture/principles.md``.
Pure domain — no filesystem, no git, no database. Everything here is about
what a valid remote *is*; how a round against it is carried out belongs to the
application layer.

Two of the rules below exist because the remote's fields end up as arguments
to the ``git`` binary. A branch name or URL that begins with ``-`` is read by
git as an option, and ``--receive-pack=<cmd>`` or ``--upload-pack=<cmd>`` is a
command git runs — so the branch is held to ``git check-ref-format --branch``
and the URL may not start with a dash. The adapter also puts ``--`` before
positional arguments wherever git accepts it, but a rule the caller cannot
reach around belongs on the value itself.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Sequence
from pathlib import PurePath

from coffer.domain.sync.errors import BackupRemoteInvalid

DEFAULT_BRANCH = "main"
DEFAULT_INTERVAL_SECONDS = 3600
DEFAULT_WORKTREE = "~/.coffer/sync"

#: Characters ``git check-ref-format`` forbids anywhere in a ref: ASCII
#: control characters, space, and ``~ ^ : ? * [ \``.
_BRANCH_FORBIDDEN_CHARS = re.compile(r"[\x00-\x20\x7f~^:?*\[\\]")
#: The shape a wire schema can check on its own, without the component rules
#: below — one ``pattern`` a surface can put on the field.
BRANCH_PATTERN = r"^[^-\s~^:?*\[\\\x00-\x1f\x7f][^\s~^:?*\[\\\x00-\x1f\x7f]*$"
URL_PATTERN = r"^[^-\s]\S*$"


def validate_branch(branch: str) -> str:
    """``branch`` stripped, or ``BackupRemoteInvalid`` if git would refuse it.

    The rules are ``git check-ref-format --branch``'s, restated so the domain
    can answer without shelling out: no leading ``-`` (an option), no ``..``
    or ``@{`` (revision syntax), no forbidden character, no component that
    starts with ``.`` or ends in ``.lock``, no empty component, no trailing
    ``.``, and not the single name ``HEAD``.
    """
    name = branch.strip()
    if not name:
        raise BackupRemoteInvalid("branch must not be empty")
    if name.startswith("-"):
        raise BackupRemoteInvalid("branch must not start with '-'")
    if _BRANCH_FORBIDDEN_CHARS.search(name):
        raise BackupRemoteInvalid("branch contains a character git does not allow")
    if ".." in name or "@{" in name:
        raise BackupRemoteInvalid("branch must not contain '..' or '@{'")
    if name == "HEAD" or name.endswith(".") or name.endswith("/") or name.startswith("/"):
        raise BackupRemoteInvalid(f"not a usable branch name: {name!r}")
    for component in name.split("/"):
        if not component:
            raise BackupRemoteInvalid("branch must not contain an empty path component")
        if component.startswith(".") or component.endswith(".lock"):
            raise BackupRemoteInvalid(f"not a usable branch name: {name!r}")
    return name


def validate_url(url: str) -> str:
    """``url`` stripped, or ``BackupRemoteInvalid`` when git would read it as
    an option rather than a remote."""
    value = url.strip()
    if not value:
        raise BackupRemoteInvalid("url must not be empty")
    if value.startswith("-"):
        raise BackupRemoteInvalid("url must not start with '-'")
    return value


@dataclasses.dataclass(frozen=True, slots=True)
class BackupRemote:
    """Where the vault converges, and how often.

    ``credential_ref`` names a secret in the credential store; the secret
    itself never lives on this object, so a remote can be logged, serialized
    into an API response or rendered in the UI without redaction.

    ``include_credentials`` is fixed here rather than per round: a remote that
    silently changed what it carried between rounds would be worse than either
    answer.
    """

    url: str
    branch: str = DEFAULT_BRANCH
    credential_ref: str | None = None
    include_credentials: bool = False
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    enabled: bool = True
    worktree_path: str = DEFAULT_WORKTREE

    def __post_init__(self) -> None:
        url = validate_url(self.url)
        branch = validate_branch(self.branch)
        if self.interval_seconds <= 0:
            raise BackupRemoteInvalid("interval must be a positive number of seconds")
        worktree = self.worktree_path.strip()
        if not worktree:
            raise BackupRemoteInvalid("worktree_path must not be empty")
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "branch", branch)
        object.__setattr__(self, "worktree_path", worktree)


def _related(a: PurePath, b: PurePath) -> bool:
    """Whether one path is the other, or lies inside it."""
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def worktree_conflict(
    worktree: PurePath,
    *,
    mirrored_roots: Sequence[PurePath],
    coffer_dir: PurePath,
    default_worktree: PurePath,
) -> str | None:
    """Why ``worktree`` may not be the working tree, or None when it may.

    The working tree is a directory Coffer ``reset --hard``s and mirrors the
    vault *into*. Placed at, inside or above a mirrored root it would mirror
    the vault into itself — an ever-deeper copy on every round — and a reset
    would erase the live files it was meant to copy. Placed at or above
    ``coffer_dir`` it would take the database and the master key with it. Inside
    ``coffer_dir`` only the default location (and anything under it) is allowed:
    that directory is Coffer's own, and nothing else under it is a working
    tree. Every path is already absolute and expanded; this is pure comparison.
    """
    if worktree == coffer_dir or coffer_dir.is_relative_to(worktree):
        return f"working tree {worktree} would contain Coffer's own directory {coffer_dir}"
    for root in mirrored_roots:
        if _related(worktree, root):
            return f"working tree {worktree} overlaps the vault directory {root}"
    if worktree.is_relative_to(coffer_dir) and not worktree.is_relative_to(default_worktree):
        return (
            f"working tree {worktree} is inside Coffer's own directory; "
            f"only {default_worktree} is allowed there"
        )
    return None


def redact(text: str, secret: str | None) -> str:
    """Replace every occurrence of ``secret`` in ``text`` with ``***``.

    Git reports an authentication failure with the URL it tried, and a token
    embedded in that URL would otherwise reach an audit row, a status field or
    a terminal. Every git error passes through here before it is stored or
    shown.
    """
    if not secret:
        return text
    return text.replace(secret, "***")
