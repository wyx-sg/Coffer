# backend/coffer-callback.spec — PyInstaller spec for the coffer-callback binary
# Usage: pyinstaller backend/coffer-callback.spec
#
# Output: dist/coffer-callback (single-file executable)
# Tauri sidecar consumes this via desktop/binaries/coffer-callback-<triple>.
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
    [],
    name="coffer-callback",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
)
