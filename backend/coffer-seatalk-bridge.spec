# backend/coffer-seatalk-bridge.spec — PyInstaller spec for the SeaTalk bridge
# Usage: pyinstaller backend/coffer-seatalk-bridge.spec
#
# Output: dist/coffer-seatalk-bridge (single-file executable)
# Runs SeaTalk's operator-supplied WebSocket SDK OUTSIDE the daemon (spec
# channels/seatalk "Load the websocket client library from an
# operator-supplied directory"). The daemon starts it beside itself; it is
# shipped in coffer-cli-<triple>.tar.gz, deployed into ~/.coffer/bin like the
# other helpers, and carried inside Coffer.app through bundle.macOS.files
# (desktop/tauri.macos.conf.json), never externalBin, which Tauri re-signs with
# the app's keychain entitlement.

# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# The SDK is imported at runtime from a directory PyInstaller never sees, so
# nothing it imports can be traced. Ship the whole standard library (minus what
# no network client uses), and the third-party packages a SeaTalk websocket
# client is likely to want, so an SDK dropped into the vendor directory finds
# its imports. Dependencies beyond these are the operator's to unpack beside it.
_STDLIB_EXCLUDES = {
    "antigravity",
    "idlelib",
    "lib2to3",
    "ensurepip",
    "pydoc_data",
    "test",
    "tkinter",
    "turtle",
    "turtledemo",
    "venv",
    "this",
    # Not built into this interpreter on macOS
    "_gdbm",
    "nis",
    "ossaudiodev",
    "spwd",
    # Windows-only
    "msilib",
    "msvcrt",
    "nt",
    "winreg",
    "winsound",
    "_winapi",
    "_overlapped",
    "_msi",
    "_wmi",
}
_STDLIB_PACKAGES = (
    "asyncio",
    "collections",
    "concurrent",
    "email",
    "encodings",
    "html",
    "http",
    "importlib",
    "json",
    "logging",
    "urllib",
    "xml",
    "zoneinfo",
)

hidden = (
    sorted(m for m in sys.stdlib_module_names if m not in _STDLIB_EXCLUDES)
    + [m for pkg in _STDLIB_PACKAGES for m in collect_submodules(pkg)]
    + collect_submodules("websockets")
    + collect_submodules("certifi")
    + collect_submodules("coffer.infrastructure.channel.seatalk_bridge")
)

datas = collect_data_files("certifi")

a = Analysis(
    ["coffer/infrastructure/channel/seatalk_bridge/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    # Marks the unpack directory with this process's pid so the daemon can
    # delete it once the process is gone (packaging/rth_unpack_owner.py).
    runtime_hooks=["packaging/rth_unpack_owner.py"],
    excludes=[
        # Nothing of the daemon belongs here — in particular nothing that can
        # reach the keychain or the vault.
        "keyring",
        "fastapi",
        "uvicorn",
        "starlette",
        "sqlalchemy",
        "aiosqlite",
        "alembic",
        "mcp",
        "openai",
        "markitdown",
        "torch",
        "mlx",
        "numba",
        "llvmlite",
        "scipy",
        "sympy",
        "networkx",
        "mpmath",
        "pandas",
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
    # UTF-8 mode, as for every Coffer binary: a launch without LANG/LC_CTYPE
    # would otherwise default text I/O to ASCII.
    [("X utf8", None, "OPTION")],
    name="coffer-seatalk-bridge",
    debug=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    target_arch=None,
    # Signed with the release's Developer ID under the hardened runtime when
    # COFFER_CODESIGN_IDENTITY is set, ad hoc otherwise — but ALWAYS with the
    # bridge's own entitlements, never $COFFER_ENTITLEMENTS_FILE: this binary
    # must not hold the keychain-access-groups entitlement the others carry
    # (desktop/entitlements/coffer-seatalk-bridge.entitlements says why).
    codesign_identity=os.environ.get("COFFER_CODESIGN_IDENTITY") or None,
    entitlements_file=os.path.join(
        os.path.dirname(os.path.abspath(SPEC)),
        "..",
        "desktop",
        "entitlements",
        "coffer-seatalk-bridge.entitlements",
    ),
)
