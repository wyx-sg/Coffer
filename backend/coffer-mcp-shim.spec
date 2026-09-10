# backend/coffer-mcp-shim.spec — PyInstaller spec for the MCP shim binary
# Usage: pyinstaller backend/coffer-mcp-shim.spec
#
# Output: dist/coffer-mcp-shim (single-file executable)
# Shipped in coffer-cli-<triple>.tar.gz; a frozen daemon deploys it into
# ~/.coffer/bin/ at startup (spec mcp-gateway FR-026) so MCP clients can launch it.

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hidden = (
    collect_submodules("coffer")
    + collect_submodules("httpx")
    + [
        "anyio._backends._asyncio",
    ]
)


a = Analysis(
    ["coffer/surfaces/shim/main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Heavy ML stack (torch/mlx/numba/scipy/…). No coffer source imports
        # any of it: transcription is remote (spec channels FR-022), so nothing
        # local decodes or runs a model. The exclude stays as a guard — a
        # transitive pull would inflate every binary from ~95 MB to ~260 MB,
        # and torch is fragile under PyInstaller.
        "torch",
        "mlx",
        "mlx_whisper",
        "numba",
        "llvmlite",
        "scipy",
        "sympy",
        "networkx",
        "mpmath",
        # The shim doesn't need most of the heavy daemon deps
        "fastapi",
        "uvicorn",
        "starlette",
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
    name="coffer-mcp-shim",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
)
