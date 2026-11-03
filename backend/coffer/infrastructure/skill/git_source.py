"""Read a skill's Git repository with this machine's own ``git``.

Spec skill-manager "Add skills from a Git repository" and "Update a
Git-imported skill from its source". Every call is one ``git`` subprocess —
never a shell, so nothing in a URL or a ref is re-parsed as a command — in an
environment that makes it safe to run unattended:

- **no prompt**: ``GIT_TERMINAL_PROMPT=0`` and the askpass variables removed,
  and SSH in batch mode, so a repository that needs a password fails with
  git's message instead of hanging the daemon;
- **only named transports**: ``GIT_ALLOW_PROTOCOL`` is the list in
  ``domain.skill.git_url`` — no ``ext::`` or ``fd::`` helper can be reached;
- **no hooks and no submodules**: a checkout runs no hook, and a submodule's
  own URL is never followed;
- **a timeout**, after which the process is killed (and a call cancelled by
  the operation's overall deadline kills its process too);
- **no background maintenance**: the clones are temporary, so no auto gc,
  maintenance or commit-graph write runs beside the next command.

A partial clone (``--filter=blob:none``) keeps the history Coffer needs to
compare commits without downloading every version of every file. Before a
checkout, the files the subpath holds are fetched **in one request**: a
checkout limited to a path would otherwise fetch each missing file on its own
(one network round trip per file), and on some git versions that sequence
fails with "in the commit graph file but not in the object database". When
the partial path still reports a missing object, the repository is cloned
once more without the filter and the checkout taken from that; this is the
only fallback (ADR ``git-source-partial-clone-prefetch``).

Unlike the vault's git (``infrastructure.sync.git_invoke``), the user's own
global git configuration is **kept**: the credential helper, SSH keys and
``insteadOf`` rules that already let this developer clone a repository are
what let Coffer read it too. Coffer supplies no credential and stores none.
Every message is passed through ``display_url`` so a token written into a URL
is never echoed back.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import re
import tempfile
from dataclasses import dataclass

from coffer.domain.git_handoff import clone_failure_details, git_missing_details
from coffer.domain.skill.git_url import ALLOWED_SCHEMES, display_url
from coffer.domain.skill_source_errors import SkillSourceUnreachable
from coffer.infrastructure.platform.host import machine_label

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 180.0
_PINNED = (
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.quotepath=false",
    "-c",
    "gc.auto=0",
    "-c",
    "maintenance.auto=false",
    "-c",
    "fetch.writeCommitGraph=false",
)
#: git's words for an object a partial clone could not get from its remote.
_MISSING_OBJECT = re.compile(
    r"promisor remote|not in the object database|missing (blob|tree|object)|"
    r"unable to read [0-9a-f]{7,}|could not fetch [0-9a-f]{7,}",
    re.IGNORECASE,
)


def missing_object(message: str) -> bool:
    """Whether a git failure is a partial clone's missing object."""
    return bool(_MISSING_OBJECT.search(message))


@dataclass(frozen=True)
class Commit:
    id: str
    subject: str


@dataclass(frozen=True)
class ChangedFile:
    status: str  # "added" | "removed" | "modified"
    path: str


def _env() -> dict[str, str]:
    env = dict(os.environ)
    for leftover in (
        "GIT_ASKPASS",
        "SSH_ASKPASS",
        "SSH_ASKPASS_REQUIRE",
        "GIT_DIR",
        "GIT_INDEX_FILE",
    ):
        env.pop(leftover, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ALLOW_PROTOCOL"] = ":".join(ALLOWED_SCHEMES)
    env["LC_ALL"] = "C"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


class GitSource:
    """The ``git`` operations a skill source needs, each one subprocess."""

    def __init__(self, *, git: str = "git", timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._git = git
        self._timeout = timeout_s

    async def _run(
        self,
        *args: str,
        cwd: pathlib.Path | None = None,
        extra_env: dict[str, str] | None = None,
        redact: str | None = None,
        check: bool = True,
        stdin: bytes | None = None,
    ) -> tuple[int, str, str]:
        env = _env()
        if extra_env:
            env.update(extra_env)
        try:
            proc = await asyncio.create_subprocess_exec(
                self._git,
                *_PINNED,
                *args,
                cwd=str(cwd) if cwd else None,
                env=env,
                stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            # Still SKILL_SOURCE_UNREACHABLE, with the install-git hand-off in
            # its details (reason "git_missing"): how git is installed depends
            # on the machine, so Coffer names no installer.
            raise SkillSourceUnreachable(
                "git is not installed on this machine",
                git_missing_details(
                    machine_label(), needed_for="adding and updating skills from a Git repository"
                ),
            ) from exc
        try:
            out, err = await asyncio.wait_for(proc.communicate(stdin), timeout=self._timeout)
        except TimeoutError as exc:
            await _kill(proc)
            raise SkillSourceUnreachable(
                f"git {_sub(args)} did not finish within {int(self._timeout)} s"
            ) from exc
        except asyncio.CancelledError:
            # The operation's overall deadline (or a shutdown) cancelled this
            # call: the process must not outlive it.
            await _kill(proc)
            raise
        stdout = out.decode("utf-8", "replace")
        stderr = err.decode("utf-8", "replace")
        code = proc.returncode or 0
        if check and code != 0:
            raise SkillSourceUnreachable(self._message(_sub(args), stderr or stdout, code, redact))
        return code, stdout, stderr

    @staticmethod
    def _message(sub: str, text: str, code: int, url: str | None) -> str:
        lines = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip() and not ln.startswith(("Cloning into", "warning: filtering"))
        ]
        detail = " ".join(lines) or f"exit {code}"
        if url:
            detail = detail.replace(url, display_url(url))
        return f"git {sub} failed: {detail}"

    async def clone(self, url: str, dest: pathlib.Path, *, partial: bool = True) -> None:
        """A bare-enough clone of ``url`` at ``dest``: history and trees, no
        checkout; with ``partial`` the blobs are left on the server until a
        checkout needs them (servers that do not support the filter send
        everything)."""
        flags = ("--filter=blob:none",) if partial else ()
        try:
            await self._run(
                "clone",
                "--quiet",
                "--no-checkout",
                *flags,
                "--",
                url,
                str(dest),
                redact=url,
            )
        except SkillSourceUnreachable as exc:
            # A missing git already carries its own hand-off; any other failed
            # clone depends on this machine's network, so it gets one too.
            if getattr(exc, "error_details", None):
                raise
            raise SkillSourceUnreachable(
                exc.git_message,
                clone_failure_details(
                    machine_label(), url=display_url(url), message=exc.git_message
                ),
            ) from exc

    async def resolve(self, repo: pathlib.Path, ref: str | None, *, url: str) -> str:
        """The full commit id ``ref`` names — a branch, then a tag, then a
        commit — or the default branch's head when ``ref`` is ``None``."""
        if ref is None:
            candidates = ["refs/remotes/origin/HEAD"]
        else:
            candidates = [f"refs/remotes/origin/{ref}", f"refs/tags/{ref}", ref]
        for candidate in candidates:
            code, out, _err = await self._run(
                "rev-parse",
                "--verify",
                "--quiet",
                "--end-of-options",
                f"{candidate}^{{commit}}",
                cwd=repo,
                check=False,
            )
            if code == 0 and out.strip():
                return out.strip()
        what = "the default branch" if ref is None else f"{ref!r}"
        raise SkillSourceUnreachable(
            f"git could not find {what} in {display_url(url)}: "
            "no branch, tag or commit by that name"
        )

    async def checkout(
        self, repo: pathlib.Path, commit: str, subpath: str, dest: pathlib.Path, *, url: str
    ) -> pathlib.Path:
        """Write the files ``subpath`` holds at ``commit`` under ``dest`` and
        return ``dest/<subpath>``. Uses its own index, so ``repo`` is untouched.

        In a partial clone the subpath's missing files are fetched in one
        request first; a missing object after that falls back, once, to a
        clone without the filter beside ``repo``."""
        dest.mkdir(parents=True, exist_ok=True)
        if await self._is_partial(repo):
            try:
                await self.prefetch(repo, commit, subpath, url=url)
                return await self._checkout(repo, commit, subpath, dest, url=url)
            except SkillSourceUnreachable as exc:
                if not missing_object(exc.git_message):
                    raise
                logger.warning(
                    "skill.git.partial_clone_fallback",
                    extra={"url": display_url(url), "error": exc.git_message},
                )
            full = repo.parent / f"{repo.name}-full"
            await self.clone(url, full, partial=False)
            repo = full
        return await self._checkout(repo, commit, subpath, dest, url=url)

    async def _checkout(
        self, repo: pathlib.Path, commit: str, subpath: str, dest: pathlib.Path, *, url: str
    ) -> pathlib.Path:
        with tempfile.TemporaryDirectory(prefix="coffer-git-index-") as tmp:
            await self._run(
                f"--git-dir={repo / '.git'}",
                f"--work-tree={dest}",
                "checkout",
                "--quiet",
                commit,
                "--",
                subpath or ".",
                cwd=dest,
                extra_env={"GIT_INDEX_FILE": str(pathlib.Path(tmp) / "index")},
                redact=url,
            )
        return dest / subpath if subpath else dest

    async def _is_partial(self, repo: pathlib.Path) -> bool:
        code, out, _e = await self._run(
            "config", "--get", "remote.origin.promisor", cwd=repo, check=False
        )
        return code == 0 and out.strip() == "true"

    async def missing(self, repo: pathlib.Path, commit: str, subpath: str) -> list[str]:
        """The objects under ``subpath`` at ``commit`` this clone does not hold
        yet; listing them fetches nothing. Empty when the path is no folder."""
        tree = await self._tree_of(repo, commit, subpath)
        if tree is None:
            return []  # the checkout reports the missing path in git's words
        _c, out, _e = await self._run("rev-list", "--objects", "--missing=print", tree, cwd=repo)
        return [ln[1:].strip() for ln in out.splitlines() if ln.startswith("?")]

    async def _tree_of(self, repo: pathlib.Path, commit: str, subpath: str) -> str | None:
        """The tree ``subpath`` names at ``commit``; ``None`` when it is no folder.
        Read from the trees alone, so nothing is fetched."""
        if not subpath:
            code, out, _e = await self._run(
                "rev-parse", "--verify", "--quiet", f"{commit}^{{tree}}", cwd=repo, check=False
            )
            return out.strip() if code == 0 and out.strip() else None
        code, out, _e = await self._run(
            "ls-tree", "--full-tree", commit, "--", subpath.rstrip("/"), cwd=repo, check=False
        )
        mode_type_oid, _, _path = out.partition("\t")
        parts = mode_type_oid.split()
        return parts[2] if code == 0 and len(parts) == 3 and parts[1] == "tree" else None

    async def prefetch(self, repo: pathlib.Path, commit: str, subpath: str, *, url: str) -> int:
        """Fetch every object ``subpath`` lacks in one request — the command
        git's own lazy fetch runs, once instead of once per file — and return
        how many were asked for."""
        wanted = await self.missing(repo, commit, subpath)
        if not wanted:
            return 0
        await self._run(
            "-c",
            "fetch.negotiationAlgorithm=noop",
            "fetch",
            "--quiet",
            "--no-tags",
            "--no-write-fetch-head",
            "--recurse-submodules=no",
            "--filter=blob:none",
            "--stdin",
            "origin",
            cwd=repo,
            redact=url,
            stdin=("\n".join(wanted) + "\n").encode(),
        )
        return len(wanted)

    async def has_commit(self, repo: pathlib.Path, commit: str) -> bool:
        code, _o, _e = await self._run(
            "cat-file", "-e", f"{commit}^{{commit}}", cwd=repo, check=False
        )
        return code == 0

    async def commits(
        self, repo: pathlib.Path, base: str, head: str, subpath: str, *, limit: int = 100
    ) -> list[Commit]:
        """The commits after ``base`` up to ``head`` that change ``subpath``, newest first."""
        known = await self.has_commit(repo, base)
        rng = f"{base}..{head}" if known else head
        _c, out, _e = await self._run(
            "log",
            f"--max-count={limit}",
            "--format=%H%x1f%s",
            rng,
            "--",
            subpath or ".",
            cwd=repo,
        )
        commits = []
        for line in out.splitlines():
            sha, _, subject = line.partition("\x1f")
            if sha:
                commits.append(Commit(sha, subject))
        return commits

    async def changed_files(
        self, repo: pathlib.Path, base: str, head: str, subpath: str
    ) -> list[ChangedFile]:
        """Files under ``subpath`` that differ between two commits, relative to it."""
        _c, out, _e = await self._run(
            "diff", "--name-status", "--no-renames", base, head, "--", subpath or ".", cwd=repo
        )
        names = {"A": "added", "D": "removed"}
        prefix = f"{subpath}/" if subpath else ""
        files = []
        for line in out.splitlines():
            status, _, path = line.partition("\t")
            if path:
                rel = path[len(prefix) :] if prefix and path.startswith(prefix) else path
                files.append(ChangedFile(names.get(status[:1], "modified"), rel))
        return files


def _sub(args: tuple[str, ...]) -> str:
    """The git subcommand among ``args``, past any ``-c`` or ``--git-dir`` options."""
    rest = list(args)
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag == "-c" and rest:
            rest.pop(0)
    return rest[0] if rest else "command"


async def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.kill()
    await proc.wait()


__all__ = ["ChangedFile", "Commit", "GitSource", "missing_object"]
