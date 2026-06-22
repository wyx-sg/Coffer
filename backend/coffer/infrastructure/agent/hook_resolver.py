"""Resolve the ``coffer-hook`` console-script binary (Slice 6).

Mirrors ``default_shim_resolver`` (``application/agent/mcp_service.py``): a
desktop- or venv-launched daemon does not inherit the shell ``PATH``, so we try,
in order: an explicit ``COFFER_HOOK_PATH`` override, a ``PATH`` lookup, the
running interpreter's own scripts directory (where pip / uv place console
scripts), then the bundled binary next to the running executable (PyInstaller).

Lives in infrastructure so the application-layer hook service (owned by another
agent) can import it; the resolver does environment/filesystem probing, which is
not domain logic.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import sysconfig

from coffer.domain.errors import ShimNotFound

_HOOK_BINARY = "coffer-hook"


def default_hook_resolver() -> str:
    """Resolve an absolute path to the ``coffer-hook`` binary.

    Tries, in order: ``COFFER_HOOK_PATH`` override → ``PATH`` lookup → the
    interpreter's ``sysconfig`` scripts dir → bundled binary next to the running
    executable. Raises ``ShimNotFound`` if none resolve.
    """
    override = os.environ.get("COFFER_HOOK_PATH")
    if override and pathlib.Path(override).exists():
        return str(pathlib.Path(override).resolve())
    found = shutil.which(_HOOK_BINARY)
    if found:
        return str(pathlib.Path(found).resolve())
    scripts_dir = sysconfig.get_path("scripts")
    if scripts_dir:
        installed = pathlib.Path(scripts_dir) / _HOOK_BINARY
        if installed.exists():
            return str(installed.resolve())
    bundled = pathlib.Path(sys.executable).resolve().parent / _HOOK_BINARY
    if bundled.exists():
        return str(bundled)
    raise ShimNotFound(_HOOK_BINARY)
