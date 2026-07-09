"""Filesystem-facing scope helpers for the memory face.

Computes the git-root of a working directory (walking up for a ``.git`` marker)
and derives a **deterministic** project id for it. The id is machine-portable
(spec 010 / ADR-043): it hashes the normalized ``origin`` remote URL when the
repo has one — the same repository maps to the same memory store on every
machine, whatever its checkout path — and falls back to the absolute-path hash
(the legacy scheme) for repos without a remote. Pure filesystem reads only.
"""

from __future__ import annotations

import configparser
import hashlib
import re
from pathlib import Path

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LEN = 26


def _nearest_git_marker(cwd: str | Path) -> Path | None:
    """The nearest ancestor of ``cwd`` (inclusive) containing a ``.git`` entry,
    or ``None``. This is the physical checkout dir — for a linked worktree it is
    the worktree itself, not the main repo. ``.git`` may be a directory (normal
    repo) or a file (worktree / submodule)."""
    start = Path(cwd).expanduser()
    try:
        start = start.resolve()
    except OSError:
        return None
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _linked_worktree_main_root(dot_git_file: Path) -> Path | None:
    """If ``.git`` is a linked-worktree pointer FILE, return the MAIN worktree's
    toplevel so every worktree of one repo shares a single project identity.

    Returns ``None`` for a submodule or any non-worktree ``.git`` file (whose
    gitdir has no ``commondir``), and for bare / ``--separate-git-dir`` layouts
    where the common dir is not a ``.git`` inside the toplevel — those keep
    their own identity via the caller's fallback.
    """
    try:
        text = dot_git_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.removeprefix("gitdir:").strip())
    if not gitdir.is_absolute():
        gitdir = dot_git_file.parent / gitdir
    # A linked worktree's gitdir contains a ``commondir`` file pointing at the
    # shared common dir; a submodule's full gitdir does not. This is the signal
    # that distinguishes "same repo, other worktree" from "a different project".
    commondir_file = gitdir / "commondir"
    try:
        rel = commondir_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    common = Path(rel)
    if not common.is_absolute():
        common = gitdir / common
    try:
        common = common.resolve()
    except OSError:
        return None
    # The common dir is normally ``<main-toplevel>/.git``; its parent is the
    # main worktree's toplevel — what ``git rev-parse --show-toplevel`` returns
    # from the main checkout, so the main and its worktrees hash identically.
    if common.name == ".git":
        return common.parent
    return None


def git_root(cwd: str | Path) -> Path | None:
    """The project root for ``cwd``, or ``None`` outside a repo.

    For a normal checkout this is the nearest ancestor containing ``.git``. For
    a linked git worktree (whose ``.git`` is a pointer FILE) it collapses to the
    MAIN repo's toplevel, so the same repo checked out in several worktrees
    resolves to ONE project store rather than one per worktree.
    """
    candidate = _nearest_git_marker(cwd)
    if candidate is None:
        return None
    dot_git = candidate / ".git"
    if dot_git.is_file():
        main_root = _linked_worktree_main_root(dot_git)
        if main_root is not None:
            return main_root
    return candidate


def git_branch(cwd: str | Path) -> str | None:
    """Current git branch for ``cwd``'s own checkout, or ``None`` outside a repo
    or on a detached HEAD with no branch. Pure filesystem read.

    Resolves against the *physical* checkout (``_nearest_git_marker``), NOT
    ``git_root`` — a linked worktree keeps its OWN branch even though
    ``git_root`` collapses its identity to the main repo, because handoffs are
    keyed per branch."""
    dot_git_dir = _nearest_git_marker(cwd)
    if dot_git_dir is None:
        return None
    dot_git = dot_git_dir / ".git"
    if dot_git.is_file():
        # linked worktree: ".git" is "gitdir: <path>"
        text = dot_git.read_text(encoding="utf-8").strip()
        gitdir = Path(text.removeprefix("gitdir:").strip())
        head = gitdir / "HEAD"
    else:
        head = dot_git / "HEAD"
    try:
        ref = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if ref.startswith("ref: refs/heads/"):
        return ref[len("ref: refs/heads/") :] or None
    return None  # detached HEAD (bare sha)


def _crockford26(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    value = int.from_bytes(digest[:16], "big")  # 128 bits, ULID-width
    out = ["0"] * _ULID_LEN
    for i in range(_ULID_LEN - 1, -1, -1):
        out[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(out)


def project_ulid(root: str | Path) -> str:
    """The LEGACY absolute-path-derived id (kept for the one-time migration of
    pre-remote-identity stores, and as the fallback for repos with no remote).

    Not a time-ordered ULID — a stable content-addressed id of the root path.
    """
    return _crockford26(str(Path(root)))


def _git_dir(root: Path) -> Path | None:
    """The repo's real git dir (handles linked worktrees + commondir)."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    if dot_git.is_file():
        try:
            text = dot_git.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        gitdir = Path(text.removeprefix("gitdir:").strip())
        if not gitdir.is_absolute():
            gitdir = (root / gitdir).resolve()
        common = gitdir / "commondir"
        if common.is_file():
            try:
                rel = common.read_text(encoding="utf-8").strip()
            except OSError:
                return gitdir
            return (gitdir / rel).resolve()
        return gitdir
    return None


def origin_remote_url(root: str | Path) -> str | None:
    """The ``origin`` remote URL from ``.git/config``, or None (pure FS read)."""
    git_dir = _git_dir(Path(root))
    if git_dir is None:
        return None
    config_path = git_dir / "config"
    if not config_path.is_file():
        return None
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read_string(config_path.read_text(encoding="utf-8"))
    except (OSError, configparser.Error):
        return None
    for section in ('remote "origin"', "remote origin"):
        if parser.has_section(section) and parser.has_option(section, "url"):
            url = parser.get(section, "url").strip()
            return url or None
    return None


_SCP_LIKE = re.compile(r"^(?:[^@/]+@)?([^:/]+):(.+)$")


def normalize_remote_url(url: str) -> str:
    """Canonical ``host/path`` for a git remote URL: ssh/https/scp-like forms of
    the same repository normalize identically (user info, ``.git`` suffix and
    case dropped)."""
    u = url.strip()
    for scheme in ("ssh://", "git://", "http://", "https://"):
        if u.lower().startswith(scheme):
            u = u[len(scheme) :]
            break
    else:
        m = _SCP_LIKE.match(u)
        if m:
            u = f"{m.group(1)}/{m.group(2)}"
    if "@" in u.split("/", 1)[0]:
        host_part, _, rest = u.partition("/")
        u = host_part.rsplit("@", 1)[1] + "/" + rest
    u = u.strip("/")
    if u.endswith(".git"):
        u = u[: -len(".git")]
    return u.lower()


def project_identity(root: str | Path) -> str:
    """Machine-portable project id: remote-URL hash, path-hash fallback."""
    url = origin_remote_url(root)
    if url:
        return _crockford26(f"remote:{normalize_remote_url(url)}")
    return project_ulid(root)
