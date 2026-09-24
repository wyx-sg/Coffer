"""Where the ``coffer`` CLI is, for the ``apiKeyHelper`` Claude Code runs.

Claude Code started from the Dock or Finder does not inherit the login shell's
``PATH``, so the helper names the CLI by absolute path. It is found the way the
MCP entry finds the shim (``application.agent.mcp_service.default_shim_resolver``):
``PATH``, then the running interpreter's scripts directory, then the binary next
to the running executable — and a deployed build is named by its public
``~/.coffer/bin/coffer`` rather than the version directory behind it, which a
later upgrade prunes. That module is another kind's, so the few lines are
repeated here rather than imported.

Unlike the shim, a CLI that cannot be found is not an error: the bare word is
what Coffer wrote before, and it still works wherever ``coffer`` is on ``PATH``.
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import sysconfig

from coffer.application.binary_deploy import user_bin_dir

_CLI_BINARY = "coffer"


def _stable_path(candidate: pathlib.Path) -> str:
    public = user_bin_dir() / _CLI_BINARY
    try:
        if public.exists() and public.resolve() == candidate.resolve():
            return str(public)
    except OSError:
        pass
    return str(candidate.resolve())


def default_coffer_cli_resolver() -> str:
    """An absolute path to the ``coffer`` CLI, or the bare name if none is found."""
    found = shutil.which(_CLI_BINARY)
    if found:
        return _stable_path(pathlib.Path(found))
    scripts_dir = sysconfig.get_path("scripts")
    if scripts_dir:
        installed = pathlib.Path(scripts_dir) / _CLI_BINARY
        if installed.exists():
            return _stable_path(installed)
    bundled = pathlib.Path(sys.executable).resolve().parent / _CLI_BINARY
    if bundled.exists():
        return _stable_path(bundled)
    return _CLI_BINARY
