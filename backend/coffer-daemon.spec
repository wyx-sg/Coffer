# backend/coffer-daemon.spec — PyInstaller spec for the daemon binary
# Usage: pyinstaller backend/coffer-daemon.spec
#
# Output: dist/coffer-daemon (single-file executable)
# Tauri sidecar consumes this via desktop/binaries/coffer-daemon-<triple>.

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


hidden = (
    collect_submodules("coffer")
    + collect_submodules("uvicorn")
    + collect_submodules("aiosqlite")
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + collect_submodules("structlog")
    + collect_submodules("mcp")
    + collect_submodules("alembic")
    # Agent config-file editing (TOML/YAML) — used by the agent MCP-install
    # and config-file services. PyInstaller usually auto-detects these from
    # `import tomlkit` / `import yaml`, but declare them explicitly so a build
    # that fails to trace them still ships a working daemon.
    + collect_submodules("tomlkit")
    + collect_submodules("yaml")
    + [
        # Anyio sniffio backend
        "anyio._backends._asyncio",
    ]
)

datas = (
    collect_data_files("alembic", include_py_files=False)
    # Ship the migrations directory so the daemon can run upgrade head
    # against a fresh DB on first launch.
    + [
        (
            "coffer/infrastructure/persistence/migrations",
            "coffer/infrastructure/persistence/migrations",
        ),
    ]
    + collect_data_files("mcp", include_py_files=False)
)

a = Analysis(
    ["coffer/infrastructure/daemon/entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Heavy test deps we don't ship
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
    name="coffer-daemon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # CLI/daemon — keep console for stderr
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
