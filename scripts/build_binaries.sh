#!/usr/bin/env bash
# Build coffer-daemon + coffer-mcp-shim with PyInstaller and stage them
# into desktop/binaries/ with target-triple suffixes for Tauri's sidecar.
#
# Usage: ./scripts/build_binaries.sh
# Requires: pyinstaller in .venv (pip install -e ./backend[dev])

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Detect the venv layout. `python -m venv` puts executables under
# `.venv/Scripts/` on Windows (git-bash / MSYS2 / Cygwin) and `.venv/bin/`
# on POSIX. Probe for the Windows layout first, fall back to POSIX.
if [ -d "$REPO_ROOT/.venv/Scripts" ]; then
    VENV_BIN="$REPO_ROOT/.venv/Scripts"
else
    VENV_BIN="$REPO_ROOT/.venv/bin"
fi

# Resolve the python interpreter (python.exe on Windows, python on POSIX).
if [ -x "$VENV_BIN/python" ]; then
    PY="$VENV_BIN/python"
elif [ -x "$VENV_BIN/python.exe" ]; then
    PY="$VENV_BIN/python.exe"
else
    PY="$VENV_BIN/python"
fi

# Invoke PyInstaller as a module (`python -m PyInstaller`) so we don't depend
# on the console-script shim path differing between layouts. Verify it's
# importable up front for a clear error.
if ! "$PY" -m PyInstaller --version >/dev/null 2>&1; then
    echo "pyinstaller not importable via $PY -m PyInstaller" >&2
    echo "run: $PY -m pip install pyinstaller" >&2
    exit 1
fi
PYINSTALLER=("$PY" -m PyInstaller)

# Detect target triple. Tauri sidecar uses the rustc target-triple format.
OS=$(uname -s)
ARCH=$(uname -m)
# Windows arch: msys/mingw uname -m returns x86_64 or aarch64; pick the
# right MSVC triple. The Windows OS patterns cover MINGW32_NT / MINGW64_NT
# / MSYS_NT / CYGWIN_NT — all of which can host pyinstaller + the Rust
# build chain via git-bash, MSYS2, or Cygwin.
case "$OS-$ARCH" in
    Darwin-x86_64)        TRIPLE="x86_64-apple-darwin" ;;
    Darwin-arm64)         TRIPLE="aarch64-apple-darwin" ;;
    Linux-x86_64)         TRIPLE="x86_64-unknown-linux-gnu" ;;
    Linux-aarch64)        TRIPLE="aarch64-unknown-linux-gnu" ;;
    MINGW*-aarch64|MSYS*-aarch64|CYGWIN*-aarch64)
                          TRIPLE="aarch64-pc-windows-msvc" ;;
    MINGW*-*|MSYS*-*|CYGWIN*-*)
                          TRIPLE="x86_64-pc-windows-msvc" ;;
    *)
        echo "unsupported platform: $OS-$ARCH" >&2
        exit 1
        ;;
esac

# Spec files live in backend/ and use paths relative to that directory.
# Run PyInstaller from backend/ so SPECPATH is correct, but redirect the
# output artefacts (dist/, build/) back to the repo root so the staging
# logic below can find them at dist/<name>[.exe].
DIST_DIR="$REPO_ROOT/dist"
BUILD_DIR="$REPO_ROOT/build"

echo ">>> Building coffer-daemon for $TRIPLE"
( cd "$REPO_ROOT/backend" && "${PYINSTALLER[@]}" --clean --noconfirm \
    --distpath "$DIST_DIR" --workpath "$BUILD_DIR" coffer-daemon.spec )
echo ">>> Building coffer-mcp-shim for $TRIPLE"
( cd "$REPO_ROOT/backend" && "${PYINSTALLER[@]}" --clean --noconfirm \
    --distpath "$DIST_DIR" --workpath "$BUILD_DIR" coffer-mcp-shim.spec )
echo ">>> Building coffer (management CLI) for $TRIPLE"
( cd "$REPO_ROOT/backend" && "${PYINSTALLER[@]}" --clean --noconfirm \
    --distpath "$DIST_DIR" --workpath "$BUILD_DIR" coffer.spec )

mkdir -p desktop/binaries

# Pick the right binary extension. Keep this set in sync with the Windows
# patterns in the triple-detection case statement above.
EXT=""
if [[ "$OS" == MINGW* || "$OS" == MSYS* || "$OS" == CYGWIN* ]]; then
    EXT=".exe"
fi

cp "dist/coffer-daemon${EXT}" "desktop/binaries/coffer-daemon-${TRIPLE}${EXT}"
cp "dist/coffer-mcp-shim${EXT}" "desktop/binaries/coffer-mcp-shim-${TRIPLE}${EXT}"
cp "dist/coffer${EXT}" "desktop/binaries/coffer-${TRIPLE}${EXT}"
chmod +x "desktop/binaries/coffer-daemon-${TRIPLE}${EXT}" \
         "desktop/binaries/coffer-mcp-shim-${TRIPLE}${EXT}" \
         "desktop/binaries/coffer-${TRIPLE}${EXT}"

echo ""
echo ">>> Built:"
ls -la "desktop/binaries/"
