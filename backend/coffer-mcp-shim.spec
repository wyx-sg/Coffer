# backend/coffer-mcp-shim.spec — PyInstaller spec for the MCP shim binary
# Usage: pyinstaller backend/coffer-mcp-shim.spec
#
# Output: a one-folder build — dist/coffer-mcp-shim.onedir/ holding the
# executable `coffer-mcp-shim` and its libraries in `coffer-mcp-shim-lib/`.
# scripts/build_binaries.sh moves both up into dist/ so they sit beside the
# other binaries; wherever the shim goes (the CLI archive, ~/.coffer/bin/<version>/,
# the app's Contents/Resources/), the two go together.
#
# One folder, not one file: every MCP session starts a shim, and a one-file
# binary unpacks its whole archive into $TMPDIR/_MEI* on each start and leaves
# it behind whenever the client kills it (ADR distribution-pyinstaller).

# -*- mode: python ; coding: utf-8 -*-

import os

# The executable finds its libraries in this folder beside itself.
LIB_DIR = "coffer-mcp-shim-lib"

a = Analysis(
    ["coffer/surfaces/shim/main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    # No collect_submodules("coffer"): the shim imports a small corner of the
    # package, and collecting all of it dragged in every daemon dependency
    # (Pillow, numpy, cryptography, keyring, test libraries) — 98 MB for a
    # process that forwards JSON-RPC over loopback. Static analysis of the
    # entry script finds what it imports.
    hiddenimports=["anyio._backends._asyncio"],
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
        # Optional imports of what the shim does pull in: pygments' image
        # formatter (Pillow, numpy), pydantic.v1's hypothesis plugin, anyio's
        # uvloop backend. None is reached at run time.
        "PIL",
        "numpy",
        "hypothesis",
        "uvloop",
        "yaml",
        "setuptools",
        "pkg_resources",
        # Daemon-side stacks the shim never touches.
        "cryptography",
        "keyring",
        "jsonschema",
        "mcp",
        "openai",
        "markitdown",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    # Run the frozen interpreter in UTF-8 mode (PEP 540). A frozen binary
    # started without LANG/LC_CTYPE -- every launch from Finder, the Dock or
    # launchd, and the desktop shell's own daemon spawn -- otherwise defaults
    # text I/O to ASCII, so reading a skill's metadata, a knowledge document or
    # any other file whose text is not ASCII fails. Development and CI never
    # reproduce it: there the C locale coerces UTF-8 mode on by itself, so the
    # unfrozen interpreter already behaves the way this option asks for.
    [("X utf8", None, "OPTION")],
    exclude_binaries=True,
    name="coffer-mcp-shim",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    target_arch=None,
    contents_directory=LIB_DIR,
    # A signed release (scripts/release_signing.sh) sets both: PyInstaller then
    # signs this executable AND every binary it collects with the Developer ID
    # under the hardened runtime. Unset — every other build — it stays
    # ad-hoc signed, exactly as before.
    codesign_identity=os.environ.get("COFFER_CODESIGN_IDENTITY") or None,
    entitlements_file=os.environ.get("COFFER_ENTITLEMENTS_FILE") or None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="coffer-mcp-shim.onedir",
)
