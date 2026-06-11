"""Shallow Git fetch of skill folders, with SSRF guard.

Public Git URLs only in v1; private repos are rejected before any clone
attempt (we cannot supply credentials).

The fetch uses `git init` + `git fetch --depth=1 <ref>` + `git checkout
FETCH_HEAD` rather than `git clone --branch <ref>`. `git clone --branch`
only accepts a branch or tag name, so a `git_ref` that is a bare commit
SHA would fail; the fetch sequence resolves branches, tags, and reachable
commit SHAs alike.

Two hardening measures supplement the SSRF guard (see `ssrf_guard`):
  * `GIT_TERMINAL_PROMPT=0` (+ empty `GIT_ASKPASS`) so an auth-required
    repo fails fast instead of blocking on an interactive prompt.
  * `http.followRedirects=false` so the network request cannot be
    redirected to an internal host after the guard validated the
    original URL.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import shutil
import tempfile
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress

from coffer.domain.errors import SourceFetchError, SSRFBlocked
from coffer.domain.skill.paths import is_within
from coffer.infrastructure.skill.ssrf_guard import check_url

# Environment for every git invocation: never prompt for credentials, so a
# private repo errors out immediately rather than hanging until timeout.
_GIT_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_ASKPASS": "",
    "GCM_INTERACTIVE": "Never",
}

# Defence-in-depth `-c` overrides prepended to network/checkout invocations.
# An empty `core.hooksPath` neutralises any repo-supplied hooks (e.g. a
# malicious `post-checkout`) so a hostile repository cannot run code during the
# fetch/checkout. Repeated on each invocation because `-c` config does not
# persist across separate `git` processes.
_HARDENING_FLAGS = ("-c", "core.hooksPath=")

# Default ceiling on the size of a fetched skill tree (FR-004). Configurable
# via ``COFFER_SKILL_MAX_CLONE_BYTES`` at process start so operators can
# raise it for a Docs/Knowledge-heavy skill repo without rebuilding the
# wheel. Values that don't parse fall back to the default.
_DEFAULT_MAX_CLONE_BYTES = 100 * 1024 * 1024


def _env_max_clone_bytes(default: int = _DEFAULT_MAX_CLONE_BYTES) -> int:
    raw = os.environ.get("COFFER_SKILL_MAX_CLONE_BYTES")
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


class GitSourceFetcher:
    """Performs a shallow Git fetch into a temporary directory.

    The caller is responsible for the tmp dir lifecycle via the
    `fetched()` async context manager.
    """

    def __init__(
        self,
        *,
        clone_timeout_seconds: float = 60.0,
        max_clone_bytes: int | None = None,
    ) -> None:
        self._timeout = clone_timeout_seconds
        # Explicit kwarg wins; otherwise honour the env var so deployments
        # can override without code changes (FR-004).
        self._max_bytes = max_clone_bytes if max_clone_bytes is not None else _env_max_clone_bytes()

    @asynccontextmanager
    async def fetched(
        self,
        *,
        git_url: str,
        git_ref: str,
        git_subpath: str = "",
    ) -> AsyncIterator[pathlib.Path]:
        """Fetch, yield the resolved subpath, then clean up.

        Yields the directory that contains the skill (the resolved subpath).
        """
        try:
            # CODE-M4: check_url performs a blocking socket.getaddrinfo DNS
            # resolution. Offload it so a slow/unresponsive resolver can't
            # freeze the daemon event loop (mirrors the keyring CODE-034 fix).
            await asyncio.to_thread(check_url, git_url)
        except ValueError as e:
            host = git_url.split("//", 1)[-1].split("/", 1)[0]
            raise SSRFBlocked(host) from e

        tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="coffer-skill-fetch-"))
        try:
            await _git_fetch_ref(
                git_url=git_url,
                git_ref=git_ref,
                dest=tmpdir,
                timeout=self._timeout,
            )
            _enforce_size_limit(tmpdir, self._max_bytes)
            subpath_dir = (tmpdir / git_subpath).resolve()
            if not is_within(subpath_dir, tmpdir.resolve()):
                raise SourceFetchError(
                    "subpath_escapes_repo",
                    {"git_subpath": git_subpath},
                )
            if not subpath_dir.is_dir():
                raise SourceFetchError(
                    "subpath_not_found",
                    {"git_subpath": git_subpath},
                )
            yield subpath_dir
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


async def _git_fetch_ref(
    *,
    git_url: str,
    git_ref: str,
    dest: pathlib.Path,
    timeout: float,
) -> None:
    """Shallow-fetch an arbitrary ref (branch, tag, or commit SHA) into `dest`.

    `git clone --branch` cannot check out a bare commit SHA; the
    init + fetch + checkout sequence handles all three ref kinds. Fetching
    a commit SHA requires the server to advertise reachable objects, which
    the major hosts (GitHub, GitLab, Bitbucket, Codeberg) all do.
    """
    # `git fetch ... <ref>` takes the ref as a positional refspec, so a
    # value starting with "-" would be parsed by git as an option. Git ref
    # names can never begin with "-", so reject it outright before invoking
    # the subprocess (option-injection guard).
    if git_ref.startswith("-"):
        raise SourceFetchError("invalid_git_ref", {"git_ref": git_ref})

    await _run_git(["init", "--quiet", "."], cwd=dest, timeout=timeout)
    await _run_git(["remote", "add", "origin", git_url], cwd=dest, timeout=timeout)
    # Default every transport to denied, then re-enable only http(s) — the
    # only schemes `check_url` lets through in production. This refuses
    # ext::, ssh, and any other transport git might otherwise attempt.
    # The `file`/local transport is enabled ONLY under the test-only knob
    # (CODE-L5): production never needs it, so shipping it always-on widened
    # the transport surface solely for the local-repo fixtures.
    protocol_flags = [
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.http.allow=always",
        "-c",
        "protocol.https.allow=always",
    ]
    if os.environ.get("COFFER_GIT_ALLOW_FILE") == "1":
        protocol_flags += ["-c", "protocol.file.allow=always"]
    await _run_git(
        [
            *_HARDENING_FLAGS,
            "-c",
            "http.followRedirects=false",
            *protocol_flags,
            "fetch",
            "--depth=1",
            "--no-recurse-submodules",
            "--quiet",
            "origin",
            git_ref,
        ],
        cwd=dest,
        timeout=timeout,
    )
    await _run_git(
        [
            *_HARDENING_FLAGS,
            "-c",
            "advice.detachedHead=false",
            "checkout",
            "--quiet",
            "--no-recurse-submodules",
            "FETCH_HEAD",
        ],
        cwd=dest,
        timeout=timeout,
    )


async def _run_git(args: Sequence[str], *, cwd: pathlib.Path, timeout: float) -> None:
    """Run one `git` invocation under `cwd`, raising SourceFetchError on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=str(cwd),
            env=_GIT_ENV,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise SourceFetchError("git_not_on_path", {}) from e
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as e:
        with suppress(ProcessLookupError):
            proc.kill()
        # Reap the killed child so it is not left as a zombie and asyncio does
        # not emit a "subprocess ... is still running" warning at GC time.
        with suppress(Exception):
            await proc.wait()
        raise SourceFetchError("fetch_timed_out", {"timeout_s": timeout}) from e
    if proc.returncode != 0:
        msg = (stderr or b"").decode("utf-8", errors="replace").strip()
        if (
            "could not read Username" in msg
            or "Authentication failed" in msg
            or "terminal prompts disabled" in msg
        ):
            raise SourceFetchError("private_repo_or_auth_required", {"stderr": msg})
        raise SourceFetchError(
            "fetch_failed",
            {"returncode": proc.returncode, "stderr": msg},
        )


def _enforce_size_limit(root: pathlib.Path, limit_bytes: int) -> None:
    total = 0
    for entry in root.rglob("*"):
        if entry.is_file() and not entry.is_symlink():
            with suppress(OSError):
                total += entry.stat().st_size
            if total > limit_bytes:
                raise SourceFetchError(
                    "clone_too_large",
                    {"limit_bytes": limit_bytes},
                )
