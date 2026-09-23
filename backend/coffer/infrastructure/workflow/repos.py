"""Giving a run its own checkout of a local repository (spec workflow
"Give a mounted repository its own checkout", "Leave the source
repository untouched on unmount").

A run advances unattended, possibly overnight. Pointing it at the developer's
working checkout would let an agent commit, stash, check out a branch or
rewrite a file over work the developer has not finished — so a mounted
repository is never the developer's tree. It is:

* **a git worktree** under the run's own ``workspace/``, on a branch of the
  run's own (``coffer/run-<short id>``), when the path is a git repository.
  The source's index, working tree and branches are untouched by it; git keeps
  the second checkout entirely in its own directory. This is also the way the
  maintainer works in this repository, so a run's checkout behaves the way its
  owner's does;
* **a link** when the path is a directory that is not a git repository. There
  is nothing to check out, and copying a tree of unknown size on a mount is
  worse than saying plainly what happened — which is what ``mount`` on the
  input records, so a node's context can say it too.

Unmounting gives back exactly what the mount took: the worktree is removed and
pruned, and the branch Coffer created goes with it, which is what makes "the
source repository is unchanged" literally true rather than nearly true.

Git runs through ``asyncio.create_subprocess_exec`` — never a shell — the same
way ``infrastructure/sync/git_mirror.py`` runs it, so a path or branch name
containing shell metacharacters is just a string.
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import shutil
from dataclasses import dataclass

from coffer.domain.error_base import CofferError
from coffer.domain.workflow.run import REPO_MOUNT_LINK, REPO_MOUNT_WORKTREE
from coffer.infrastructure.workflow import paths

__all__ = ["MountedRepo", "RepoMountError", "mount_repo", "unmount_repo"]

_logger = logging.getLogger(__name__)

#: Seconds any one git invocation gets. A worktree add on a large repository is
#: a checkout, so this is generous; what it exists for is the hung credential
#: prompt, not the slow disk.
GIT_TIMEOUT_S = 120.0

#: The branch a run's checkout sits on. Namespaced under ``coffer/`` so it can
#: never collide with a branch the developer would write by hand, and carrying
#: the run id so two runs over one repository do not share one.
BRANCH_PREFIX = "coffer/run-"
_SHORT_ID = 12

#: Git's own knobs, pinned on every call: never prompt for credentials (a run
#: is unattended, and a prompt is a hang), and never read the developer's
#: aliases, which could redefine a subcommand out from under us.
_PINNED = ("-c", "core.askpass=", "-c", "credential.helper=")


class RepoMountError(CofferError):
    """A repository input that could not be given to the run.

    Raised rather than half-mounted: an input row pointing at a checkout that
    does not exist is a node told to work somewhere that is not there.
    """

    code = "WORKFLOW_REPO_MOUNT_FAILED"

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"cannot mount repository {source!r}: {reason}")
        self.source = source
        self.reason = reason


@dataclass(frozen=True)
class MountedRepo:
    """What the run was given, and where."""

    #: The directory name inside ``workspace/``.
    name: str
    #: That directory's absolute path — what a node opens.
    path: str
    #: The source, resolved. Recorded so unmounting can reach the repository
    #: that owns the worktree even if the developer has since moved on.
    source: str
    #: ``worktree`` or ``link`` (``domain.workflow.run``).
    mount: str
    #: The branch Coffer created, for a worktree; ``None`` for a link.
    branch: str | None = None

    @property
    def isolated(self) -> bool:
        return self.mount == REPO_MOUNT_WORKTREE


async def mount_repo(
    run_id: str, source: str, *, taken: frozenset[str] = frozenset()
) -> MountedRepo:
    """Give the run its own checkout of ``source`` inside its workspace."""
    resolved = _resolve(source)
    name = _checkout_name(resolved, taken)
    target = paths.workspace_path(run_id, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise RepoMountError(source, f"{name!r} is already in this run's working directory")
    if not await _is_git_repo(resolved):
        target.symlink_to(resolved, target_is_directory=True)
        return MountedRepo(name=name, path=str(target), source=str(resolved), mount=REPO_MOUNT_LINK)
    branch = f"{BRANCH_PREFIX}{run_id[:_SHORT_ID]}"
    await _git(resolved, "worktree", "add", "-b", branch, str(target), "HEAD", source=source)
    return MountedRepo(
        name=name,
        path=str(target),
        source=str(resolved),
        mount=REPO_MOUNT_WORKTREE,
        branch=branch,
    )


async def unmount_repo(run_id: str, *, source: str, path: str, mount: str) -> None:
    """Take back exactly what the mount gave, and nothing else (spec
    workflow "Leave the source repository untouched on unmount").

    Takes the three things the input row records rather than the value object
    the mount returned: the row is what survives a daemon restart, and an
    unmount that needed something the row does not carry would be an unmount
    that only worked in the session that mounted.

    Best effort by design. The developer may have deleted the source since, or
    removed the worktree by hand; neither is a reason to refuse to unmount the
    input, because the row is the thing they asked to be gone. What is never
    best effort is the source: nothing here writes to its working tree, and the
    only branch it deletes is the one this module created.
    """
    name = pathlib.PurePosixPath(path).name
    paths.check_segment(name)
    parent = paths.workspace_dir(run_id)
    paths.assert_inside_run(parent, run_id)
    target = parent / name
    if mount != REPO_MOUNT_WORKTREE:
        # ``unlink`` removes the link, never what it points at.
        if target.is_symlink() or target.is_file():
            target.unlink()
        return
    await _remove_worktree(run_id, pathlib.Path(source), target)


async def _remove_worktree(run_id: str, source: pathlib.Path, target: pathlib.Path) -> None:
    if source.is_dir():
        await _git(source, "worktree", "remove", "--force", str(target), check=False)
        await _git(source, "worktree", "prune", check=False)
        # The branch was Coffer's, created by the mount. Deleting it is what
        # makes the source's branch list exactly what it was before.
        branch = f"{BRANCH_PREFIX}{run_id[:_SHORT_ID]}"
        await _git(source, "branch", "-D", "--", branch, check=False)
    if target.is_dir() and not target.is_symlink():
        # Git leaves the directory behind when its administrative file is
        # already gone; the run's workspace is ours to tidy either way.
        shutil.rmtree(target, ignore_errors=True)


def _resolve(source: str) -> pathlib.Path:
    """``source`` as an existing directory, or a refusal that says why."""
    if not source.strip():
        raise RepoMountError(source, "no path given")
    candidate = pathlib.Path(source).expanduser()
    if not candidate.is_absolute():
        raise RepoMountError(source, "a repository input is an absolute path")
    if not candidate.exists():
        raise RepoMountError(source, "no such directory")
    if not candidate.is_dir():
        raise RepoMountError(source, "not a directory")
    return candidate.resolve()


def _checkout_name(resolved: pathlib.Path, taken: frozenset[str]) -> str:
    """The directory name the checkout gets, guarded and de-duplicated."""
    base = resolved.name or "repo"
    try:
        paths.check_segment(base)
    except paths.UnsafeWorkflowPath:
        raise RepoMountError(str(resolved), f"{base!r} is not a usable directory name") from None
    if base not in taken:
        return base
    counter = 2
    while f"{base}-{counter}" in taken:
        counter += 1
    return f"{base}-{counter}"


async def _is_git_repo(path: pathlib.Path) -> bool:
    done = await _git(path, "rev-parse", "--is-inside-work-tree", check=False)
    return done[0] == 0 and done[1].strip() == "true"


async def _git(
    cwd: pathlib.Path,
    *args: str,
    check: bool = True,
    source: str | None = None,
) -> tuple[int, str, str]:
    """Run one git command in ``cwd``; return ``(code, stdout, stderr)``."""
    argv = ("git", "-C", str(cwd), *_PINNED, *args)
    pipe = asyncio.subprocess.PIPE
    try:
        proc = await asyncio.create_subprocess_exec(*argv, stdout=pipe, stderr=pipe)
    except OSError as exc:  # pragma: no cover - git missing from PATH
        if check:
            raise RepoMountError(source or str(cwd), f"git could not be run: {exc}") from exc
        return 1, "", str(exc)
    try:
        raw_out, raw_err = await asyncio.wait_for(proc.communicate(), timeout=GIT_TIMEOUT_S)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        if check:
            raise RepoMountError(
                source or str(cwd), f"git {args[0]} timed out after {GIT_TIMEOUT_S:.0f}s"
            ) from None
        return 1, "", "timed out"
    out = raw_out.decode("utf-8", errors="replace")
    err = raw_err.decode("utf-8", errors="replace")
    code = proc.returncode or 0
    if code != 0:
        if check:
            raise RepoMountError(source or str(cwd), err.strip() or out.strip() or f"exit {code}")
        _logger.debug("workflow.repo.git_failed", extra={"args": args, "code": code})
    return code, out, err
