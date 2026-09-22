# backend/coffer-callback.spec — PyInstaller spec for the coffer-callback binary
# Usage: pyinstaller backend/coffer-callback.spec
#
# Output: dist/coffer-callback (single-file executable)
# Shipped in coffer-cli-<triple>.tar.gz; a frozen daemon deploys it into
# ~/.coffer/bin/ at startup (spec daemon FR-027) because it spawns it at runtime.
#
# The callback listener is the SeaTalk webhook-ingress child the daemon spawns
# (channel/listener_spawn.py resolves it as a sibling of the frozen daemon).
# It serves one FastAPI route under uvicorn and forwards events to the daemon
# over httpx, so — unlike the lean coffer-hook/coffer-mcp-shim — it MUST keep
# fastapi/uvicorn/starlette/httpx. It still drops the daemon-only heavy deps
# (sqlalchemy/aiosqlite/alembic/structlog) that collect_submodules("coffer")
# would otherwise drag in via the persistence layer it never touches.

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hidden = (
    collect_submodules("coffer")
    # uvicorn imports its event-loop/protocol backends lazily by string name,
    # and httpx picks its transport at runtime — PyInstaller's static graph
    # misses both, so collect them explicitly.
    + collect_submodules("uvicorn")
    + collect_submodules("httpx")
    + [
        "anyio._backends._asyncio",
    ]
)


a = Analysis(
    ["coffer/surfaces/callback/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Heavy ML stack (torch/mlx/numba/scipy/…). No coffer source imports
        # any of it: nothing local decodes audio or runs a model — voice is
        # transcribed through the user's own connection (spec channels FR-019).
        # The exclude stays as a guard — a transitive pull would inflate every
        # binary from ~95 MB to ~260 MB, and torch is fragile under PyInstaller.
        "torch",
        "mlx",
        "numba",
        "llvmlite",
        "scipy",
        "sympy",
        "networkx",
        "mpmath",
        # Daemon-only deps the listener never imports at runtime. Dropping them
        # keeps this sidecar small even though collect_submodules("coffer")
        # lists the persistence modules that import them at module scope.
        "sqlalchemy",
        "aiosqlite",
        "alembic",
        "structlog",
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
    name="coffer-callback",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
)
