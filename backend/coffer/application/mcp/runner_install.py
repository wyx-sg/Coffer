"""Missing-runner detection + one-click install for stdio MCP servers
(spec 001 amendment 2026-07-10).

A synced stdio server references a launcher command (``uvx``, ``npx``, …)
that may not exist on this machine — the server then shows as failing with
no hint that the fix is "install the runner". Detection is a PATH lookup on
the command's basename; installation is a FIXED allowlist of runner →
Homebrew formula (never an arbitrary command from config): the runner is a
launcher the user's own server config names, and the actual MCP package is
fetched by the launcher itself on first run (uvx/npx semantics).
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

from coffer.domain.error_base import CofferError

# runner basename -> (display name, brew formula). Deliberately tiny: only
# self-fetching launchers whose install is unambiguous.
_INSTALLABLE: dict[str, tuple[str, str]] = {
    "uvx": ("uv", "uv"),
    "uv": ("uv", "uv"),
    "npx": ("Node.js", "node"),
    "node": ("Node.js", "node"),
    "bunx": ("Bun", "bun"),
    "bun": ("Bun", "bun"),
}

_INSTALL_TIMEOUT_SECONDS = 900


class RunnerInstallUnsupported(CofferError):  # noqa: N818
    """The missing command has no known unambiguous install. Maps to 422."""

    code = "MCP_RUNNER_INSTALL_UNSUPPORTED"

    def __init__(self, runner: str) -> None:
        super().__init__(f"no known install for runner {runner!r}; install it manually")
        self.runner = runner


class RunnerInstallFailed(CofferError):  # noqa: N818
    """The package-manager install returned non-zero. Maps to 422."""

    code = "MCP_RUNNER_INSTALL_FAILED"

    def __init__(self, runner: str, detail: str) -> None:
        super().__init__(f"installing {runner!r} failed: {detail}")
        self.runner = runner
        self.detail = detail


def missing_runner(command: str) -> str | None:
    """The command's basename when it cannot be resolved on this machine.

    An absolute path checks existence directly; a bare name goes through
    PATH. None = the runner resolves (whatever health says is not this)."""
    if not command:
        return None
    path = pathlib.Path(command)
    if path.is_absolute():
        return None if path.exists() else path.name
    return None if shutil.which(command) else path.name


def runner_installable(runner: str) -> bool:
    return runner in _INSTALLABLE


def install_runner(runner: str) -> str:
    """Install a missing runner via its allowlisted Homebrew formula; returns
    the formula name. Blocking (brew can take minutes) — call off the loop."""
    entry = _INSTALLABLE.get(runner)
    if entry is None or shutil.which("brew") is None:
        raise RunnerInstallUnsupported(runner)
    _display, formula = entry
    try:
        proc = subprocess.run(
            ["brew", "install", formula],
            capture_output=True,
            text=True,
            check=False,
            timeout=_INSTALL_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        raise RunnerInstallFailed(
            runner, f"timed out after {_INSTALL_TIMEOUT_SECONDS}s"
        ) from e
    if proc.returncode != 0:
        raise RunnerInstallFailed(runner, proc.stderr.strip()[-500:])
    return formula
