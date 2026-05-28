#!/usr/bin/env bash
# Build coffer-daemon + coffer-mcp-shim with PyInstaller and stage them
# into desktop/binaries/ with target-triple suffixes for Tauri's sidecar.
#
# Usage: ./scripts/build_binaries.sh
# Requires: pyinstaller in .venv (pip install -e ./backend[dev])

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PY="$REPO_ROOT/.venv/bin/python"
PYINSTALLER="$REPO_ROOT/.venv/bin/pyinstaller"

if [ ! -x "$PYINSTALLER" ]; then
    echo "pyinstaller not found at $PYINSTALLER" >&2
    echo "run: $PY -m pip install pyinstaller" >&2
    exit 1
fi

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

echo ">>> Building coffer-daemon for $TRIPLE"
"$PYINSTALLER" --clean --noconfirm backend/coffer-daemon.spec
echo ">>> Building coffer-mcp-shim for $TRIPLE"
"$PYINSTALLER" --clean --noconfirm backend/coffer-mcp-shim.spec

mkdir -p desktop/binaries

# Pick the right binary extension. Keep this set in sync with the Windows
# patterns in the triple-detection case statement above.
EXT=""
if [[ "$OS" == MINGW* || "$OS" == MSYS* || "$OS" == CYGWIN* ]]; then
    EXT=".exe"
fi

cp "dist/coffer-daemon${EXT}" "desktop/binaries/coffer-daemon-${TRIPLE}${EXT}"
cp "dist/coffer-mcp-shim${EXT}" "desktop/binaries/coffer-mcp-shim-${TRIPLE}${EXT}"
chmod +x "desktop/binaries/coffer-daemon-${TRIPLE}${EXT}" \
         "desktop/binaries/coffer-mcp-shim-${TRIPLE}${EXT}"

echo ""
echo ">>> Built:"
ls -la "desktop/binaries/"
