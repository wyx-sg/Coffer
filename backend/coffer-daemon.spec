# backend/coffer-daemon.spec — PyInstaller spec for the daemon binary
# Usage: pyinstaller backend/coffer-daemon.spec
#
# Output: dist/coffer-daemon (single-file executable)
# Ships the built web UI (frontend/dist) as `webui/` — the daemon serves it
# itself now that the desktop shell is gone (spec mcp-gateway FR-024).

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
    # Knowledge-layer and turn-platform deps. These are imported LAZILY
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

# The built web UI. The daemon serves this at its own loopback origin, so a
# frozen build must carry it. Built by `npm run build` before PyInstaller runs
# (see .github/workflows/release.yml); when it is absent — a backend-only local
# build — the daemon simply serves the API and `webui.resolve_webui_dir()`
# returns None, so the build still succeeds rather than failing on a missing
# directory PyInstaller would otherwise reject.
import os as _os

_webui_dist = _os.path.join(_os.path.dirname(_os.path.abspath(SPEC)), "..", "frontend", "dist")
if _os.path.isfile(_os.path.join(_webui_dist, "index.html")):
    datas = datas + [(_webui_dist, "webui")]

a = Analysis(
    ["coffer/infrastructure/daemon/entry.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
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
