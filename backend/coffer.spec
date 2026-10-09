# backend/coffer.spec — PyInstaller spec for the coffer management CLI binary
# Usage: pyinstaller backend/coffer.spec
#
# Output: dist/coffer (single-file executable)
# Packaged into coffer-cli-<triple>.tar.gz beside the daemon and shim; the
# frozen detect-or-spawn resolution needs them co-located (ADR daemon-detect-or-spawn).
#
# The CLI is a thin HTTP client — it does NOT embed FastAPI / uvicorn /
# SQLAlchemy / Alembic / the MCP SDK.  Those live only in the daemon binary.

# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_submodules


hidden = (
    collect_submodules("coffer.surfaces.cli")
    + collect_submodules("coffer.infrastructure.daemon")
    + collect_submodules("typer")
    + collect_submodules("click")
    + collect_submodules("httpx")
    + collect_submodules("pydantic")
    + collect_submodules("keyring")
    # `coffer --show-completion` / `--install-completion` ask shellingham which
    # shell runs them; it imports its platform module (`shellingham.posix`,
    # `shellingham.nt`) by name at run time, which PyInstaller cannot see.
    + collect_submodules("shellingham")
    + [
        # Anyio sniffio backend (pulled in by httpx/anyio)
        "anyio._backends._asyncio",
        # keyring platform backends — include all so the frozen binary works
        # across macOS (Keychain), Linux (SecretService / kwallet), and
        # Windows (WinCred).  PyInstaller misses these because they are
        # loaded at runtime via entry_points.
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
        "keyring.backends.Windows",
        "keyring.backends.fail",
        "keyring.backends.null",
    ]
)


a = Analysis(
    ["coffer/surfaces/cli/main.py"],
    pathex=["."],
    binaries=[],
    # No data files: everything this binary runs is an importable module.
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    # Marks the unpack directory with this process's pid so the daemon can
    # delete it once the process is gone (packaging/rth_unpack_owner.py).
    runtime_hooks=["packaging/rth_unpack_owner.py"],
    excludes=[
        # Heavy ML stack no coffer binary ships. No coffer source imports any
        # of it — nothing local decodes audio or runs a model; the exclude
        # documents the invariant and guards against a future transitive pull.
        "torch",
        "mlx",
        "numba",
        "llvmlite",
        "scipy",
        "sympy",
        "networkx",
        "mpmath",
        # Daemon-only heavy deps — the CLI does NOT need these
        "fastapi",
        "uvicorn",
        "starlette",
        "sqlalchemy",
        "aiosqlite",
        "alembic",
        "structlog",
        "mcp",
        # Test/lint tooling
        "pytest",
        "pytest_asyncio",
        "pytest_cov",
        "ruff",
        "mypy",
        "import_linter",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    # Run the frozen interpreter in UTF-8 mode (PEP 540). A frozen binary
    # started without LANG/LC_CTYPE -- every launch from Finder, the Dock or
    # launchd, and the desktop shell's own daemon spawn -- otherwise defaults
    # text I/O to ASCII, so reading a skill's metadata, a knowledge document or
    # any other file whose text is not ASCII fails. Development and CI never
    # reproduce it: there the C locale coerces UTF-8 mode on by itself, so the
    # unfrozen interpreter already behaves the way this option asks for.
    [("X utf8", None, "OPTION")],
    name="coffer",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
    # A signed release (scripts/release_signing.sh) sets both: PyInstaller then
    # signs this executable AND every binary it collects with the Developer ID
    # under the hardened runtime, so the libraries a one-file build unpacks at
    # start pass library validation. Unset — every other build — it stays
    # ad-hoc signed, exactly as before.
    codesign_identity=os.environ.get("COFFER_CODESIGN_IDENTITY") or None,
    entitlements_file=os.environ.get("COFFER_ENTITLEMENTS_FILE") or None,
)
