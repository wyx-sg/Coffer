# backend/coffer-mcp-shim.spec — PyInstaller spec for the MCP shim binary
# Usage: pyinstaller backend/coffer-mcp-shim.spec
#
# Output: dist/coffer-mcp-shim (single-file executable)
# Shipped in coffer-cli-<triple>.tar.gz; a frozen daemon deploys it into
# ~/.coffer/bin/ at startup (spec daemon FR-027) so MCP clients can launch it.

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
    # Run the frozen interpreter in UTF-8 mode (PEP 540). A frozen binary
    # started without LANG/LC_CTYPE -- every launch from Finder, the Dock or
    # launchd, and the desktop shell's own daemon spawn -- otherwise defaults
    # text I/O to ASCII, so reading a skill's metadata, a knowledge document or
    # any other file whose text is not ASCII fails. Development and CI never
    # reproduce it: there the C locale coerces UTF-8 mode on by itself, so the
    # unfrozen interpreter already behaves the way this option asks for.
    [("X utf8", None, "OPTION")],
    name="coffer-mcp-shim",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
)
