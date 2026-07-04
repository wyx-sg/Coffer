# backend/coffer.spec — PyInstaller spec for the coffer management CLI binary
# Usage: pyinstaller backend/coffer.spec
#
# Output: dist/coffer (single-file executable)
# Tauri sidecar consumes this via desktop/binaries/coffer-<triple>.
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
    datas=[],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Heavy ML stack from the [voice] extra — no coffer binary ships
        # torch/mlx (the frozen app uses the whisper-cli sidecar, ADR-039).
        # The CLI never imports these; the exclude documents the invariant and
        # guards against a future transitive pull.
        "torch",
        "mlx",
        "mlx_whisper",
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
    [],
    name="coffer",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
)
