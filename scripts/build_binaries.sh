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
echo ">>> Building coffer-hook for $TRIPLE"
( cd "$REPO_ROOT/backend" && "${PYINSTALLER[@]}" --clean --noconfirm \
    --distpath "$DIST_DIR" --workpath "$BUILD_DIR" coffer-hook.spec )
echo ">>> Building coffer-callback for $TRIPLE"
( cd "$REPO_ROOT/backend" && "${PYINSTALLER[@]}" --clean --noconfirm \
    --distpath "$DIST_DIR" --workpath "$BUILD_DIR" coffer-callback.spec )

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
cp "dist/coffer-hook${EXT}" "desktop/binaries/coffer-hook-${TRIPLE}${EXT}"
cp "dist/coffer-callback${EXT}" "desktop/binaries/coffer-callback-${TRIPLE}${EXT}"
chmod +x "desktop/binaries/coffer-daemon-${TRIPLE}${EXT}" \
         "desktop/binaries/coffer-mcp-shim-${TRIPLE}${EXT}" \
         "desktop/binaries/coffer-${TRIPLE}${EXT}" \
         "desktop/binaries/coffer-hook-${TRIPLE}${EXT}" \
         "desktop/binaries/coffer-callback-${TRIPLE}${EXT}"

# ---------------------------------------------------------------------------
# whisper-cli — torch-free local STT engine for the frozen app (ADR-039).
# A self-contained `whisper-cli` (static libs; on Apple Silicon Metal is
# default-on and its shader is EMBEDDED so only Command Line Tools are needed —
# no full Xcode). The pinned source is cached under build/whisper.cpp so a
# repeat bundle re-uses the checkout and cmake's incremental build.
# ---------------------------------------------------------------------------
WHISPER_TAG="v1.9.1"
WHISPER_SRC="$BUILD_DIR/whisper.cpp"
WHISPER_BUILD="$WHISPER_SRC/build"

if ! command -v cmake >/dev/null 2>&1; then
    echo "error: cmake is required to build the whisper-cli STT sidecar (ADR-039)." >&2
    echo "  install it: 'brew install cmake' (macOS) or your platform's package manager." >&2
    exit 1
fi

# Re-clone if the cache is absent or pinned to a different tag.
if [ -d "$WHISPER_SRC/.git" ]; then
    CACHED_TAG="$(git -C "$WHISPER_SRC" describe --tags --exact-match 2>/dev/null || echo none)"
    if [ "$CACHED_TAG" != "$WHISPER_TAG" ]; then
        echo ">>> cached whisper.cpp is '$CACHED_TAG', want '$WHISPER_TAG' — re-cloning"
        rm -rf "$WHISPER_SRC"
    fi
fi
if [ ! -d "$WHISPER_SRC/.git" ]; then
    echo ">>> Cloning whisper.cpp $WHISPER_TAG"
    git clone --depth 1 --branch "$WHISPER_TAG" \
        https://github.com/ggml-org/whisper.cpp "$WHISPER_SRC"
fi

WHISPER_CMAKE_FLAGS=(
    -DCMAKE_BUILD_TYPE=Release
    -DBUILD_SHARED_LIBS=OFF
    -DWHISPER_BUILD_TESTS=OFF
    -DWHISPER_BUILD_EXAMPLES=ON
)
if [ "$OS" = "Darwin" ]; then
    WHISPER_CMAKE_FLAGS+=(-DGGML_METAL_EMBED_LIBRARY=ON)
fi

echo ">>> Building whisper-cli $WHISPER_TAG for $TRIPLE"
cmake -S "$WHISPER_SRC" -B "$WHISPER_BUILD" "${WHISPER_CMAKE_FLAGS[@]}"
cmake --build "$WHISPER_BUILD" --config Release -j --target whisper-cli

WHISPER_CLI="$WHISPER_BUILD/bin/whisper-cli${EXT}"
if [ ! -x "$WHISPER_CLI" ]; then
    echo "error: whisper-cli was not produced at $WHISPER_CLI" >&2
    exit 1
fi
cp "$WHISPER_CLI" "desktop/binaries/whisper-cli-${TRIPLE}${EXT}"
chmod +x "desktop/binaries/whisper-cli-${TRIPLE}${EXT}"

echo ""
echo ">>> Built:"
ls -la "desktop/binaries/"
