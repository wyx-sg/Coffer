# backend/coffer-mcp-shim.spec — PyInstaller spec for the MCP shim binary
# Usage: pyinstaller backend/coffer-mcp-shim.spec
#
# Output: dist/coffer-mcp-shim (single-file executable)
# Shipped in coffer-cli-<triple>.tar.gz; a frozen daemon deploys it into
# ~/.coffer/bin/ at startup (spec daemon "Deploy frozen sibling binaries and
# back up the history database before migrating") so MCP clients can launch it.

# -*- mode: python ; coding: utf-8 -*-

import os

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
        # transcribed through the user's own connection (spec channels
        # "Transcribe inbound voice only when the user opted in").
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
    # A signed release (scripts/release_signing.sh) sets both: PyInstaller then
    # signs this executable AND every binary it collects with the Developer ID
    # under the hardened runtime, so the libraries a one-file build unpacks at
    # start pass library validation. Unset — every other build — it stays
    # ad-hoc signed, exactly as before.
    codesign_identity=os.environ.get("COFFER_CODESIGN_IDENTITY") or None,
    entitlements_file=os.environ.get("COFFER_ENTITLEMENTS_FILE") or None,
)
