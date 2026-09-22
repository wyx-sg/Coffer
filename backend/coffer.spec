# backend/coffer.spec — PyInstaller spec for the coffer management CLI binary
# Usage: pyinstaller backend/coffer.spec
#
# Output: dist/coffer (single-file executable)
# Packaged into coffer-cli-<triple>.tar.gz beside the daemon and shim; the
# frozen detect-or-spawn resolution needs them co-located (ADR daemon-detect-or-spawn).
#
# The CLI is a thin HTTP client — it does NOT embed FastAPI / uvicorn /
# SQLAlchemy / Alembic.  Those live only in the daemon binary.

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hidden = (
    collect_submodules("coffer.surfaces.cli")
    + collect_submodules("coffer.infrastructure.daemon")
    + collect_submodules("typer")
    + collect_submodules("click")
    + collect_submodules("httpx")
    + collect_submodules("pydantic")
    + collect_submodules("keyring")
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
    # No data files: the knowledge skill this binary used to carry as an asset
    # directory is rendered per agent in code now, so there is nothing here
    # that is not an importable module.
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
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
    # text I/O to ASCII, so reading a skill's metadata, a workflow template or
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
)
