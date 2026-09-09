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
    # KB/memory/chat deps (specs 006/007/008). These are imported LAZILY
    # (inside functions) so the daemon ships even when an extra is missing —
    # which is exactly why PyInstaller's static analysis cannot trace them.
    # Declare them explicitly so a frozen build can convert documents, embed,
    # run the sqlite-vec vector index, and drive the built-in chat agent.
    #   sqlite_vec — knowledge/vec_index.py (also needs its data files below)
    #   markitdown — knowledge/converters/markitdown_converter.py
    #   openai     — knowledge/embeddings.py
    #   langgraph / langchain — chat/*
    + collect_submodules("sqlite_vec")
    + collect_submodules("markitdown")
    # MarkItDown imports its format backends lazily *inside* each converter.
    # PyInstaller's import graph MAY trace them transitively (the converter
    # modules do import them at module scope), but list the readers behind the
    # markitdown[docx,pdf,pptx,xls,xlsx] extras explicitly as belt-and-suspenders
    # so a build that fails to trace them still ships working converters instead
    # of raising MissingDependencyException (PDF was the one that bit a user).
    + collect_submodules("pdfminer")
    + collect_submodules("pdfplumber")
    + collect_submodules("pptx")
    + collect_submodules("mammoth")
    + collect_submodules("openpyxl")
    + collect_submodules("pandas")
    + collect_submodules("xlrd")
    + collect_submodules("openai")
    + collect_submodules("langgraph")
    + collect_submodules("langchain")
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
    # sqlite-vec ships its loadable native extension (vec0.dylib / vec0.so /
    # vec0.dll) as PACKAGE DATA, not a Python submodule — collect_submodules
    # above never captures it. Without this the frozen daemon cannot load the
    # vec0 extension and vector retrieval silently degrades to keyword-only
    # (VecIndex.available() swallows the load failure).
    + collect_data_files("sqlite_vec")
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
        # Heavy ML stack pulled in transitively by the [voice] extra's
        # mlx-whisper (torch/mlx/numba/scipy/…). transcribe.py imports
        # mlx_whisper LAZILY, but PyInstaller scans function bodies and would
        # bundle the whole ~700 MB stack whenever [voice] is installed in the
        # build venv — inflating every binary from ~95 MB to ~260 MB (and torch
        # is fragile under PyInstaller). The frozen app transcribes via the
        # bundled torch-free whisper-cli sidecar instead (ADR-039), so no coffer
        # binary ever needs these. No coffer source imports them directly.
        "torch",
        "mlx",
        "mlx_whisper",
        "numba",
        "llvmlite",
        "scipy",
        "sympy",
        "networkx",
        "mpmath",
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
