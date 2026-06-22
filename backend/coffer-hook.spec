# backend/coffer-hook.spec — PyInstaller spec for the coffer-hook binary
# Usage: pyinstaller backend/coffer-hook.spec
#
# Output: dist/coffer-hook (single-file executable)
# Tauri sidecar consumes this via desktop/binaries/coffer-hook-<triple>.
#
# The SessionStart hook is a tiny CLI (argparse + urllib, talks to the daemon
# over HTTP) — it needs the coffer package but none of the heavy daemon deps,
# so it mirrors coffer-mcp-shim.spec's lean exclude list.

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hidden = collect_submodules("coffer") + [
    "anyio._backends._asyncio",
]


a = Analysis(
    ["coffer/surfaces/hook/main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # The hook doesn't need the heavy daemon deps.
        "fastapi",
        "uvicorn",
        "starlette",
        "sqlalchemy",
        "aiosqlite",
        "alembic",
        "structlog",
        "httpx",
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
    name="coffer-hook",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
)
