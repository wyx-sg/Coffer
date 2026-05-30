#!/usr/bin/env bash
# smoke_test_bundle.sh — Verify the embedded binaries in a built Coffer bundle.
#
# Usage:
#   ./scripts/smoke_test_bundle.sh <path-to-bundle-root>
#
# Accepted bundle layouts:
#   macOS .app dir:  ./Coffer.app
#   Linux unpacked:  ./coffer-desktop_<version>_amd64/  (from deb/AppImage mount)
#   Windows install: C:\Program Files\Coffer\  (run under Git Bash or WSL)
#
# What it does:
#   1. Locate coffer-mcp-shim AND coffer-daemon inside the bundle.
#   2. Start the bundled coffer-daemon under an isolated HOME and wait until it
#      has published ~/.coffer/daemon.json and is answering /daemon/status.
#   3. Spawn the shim with the SAME isolated HOME, send one JSON-RPC 2.0
#      "initialize" request over stdin, and assert a well-formed reply comes
#      back within 15 s — exercising the real shim -> daemon /mcp round-trip.
#   4. Tear the daemon down and exit 0 on success; non-zero with diagnostics
#      on failure.
#
# The shim only replies once it reaches a live coffer-daemon, and its
# auto-spawn fallback (sys.executable -m ...) does NOT work inside a frozen
# PyInstaller binary — so this script starts the bundled daemon itself rather
# than relying on that fallback.
#
# An explicit daemon path may be passed as the second argument; otherwise it
# is probed next to the shim using the same per-platform layout list.
#
# The test does NOT start the full Tauri GUI — it exercises the sidecar binaries
# directly.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

BUNDLE="${1:?usage: $0 <bundle-path> [daemon-path]}"
DAEMON_ARG="${2:-}"

if [ ! -d "$BUNDLE" ] && [ ! -f "$BUNDLE" ]; then
    echo "error: bundle path does not exist: $BUNDLE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate a bundled sidecar binary by name. Probes the same per-platform
# layouts for both coffer-mcp-shim and coffer-daemon.
#
# The candidate directory set MUST stay aligned with the canonical sidecar
# layout in desktop/src/shim.rs::resolve_sidecar — that Rust function is the
# source of truth for where Tauri 2 stages externalBin per platform:
#   * macOS:  Coffer.app/Contents/MacOS/<binary> (sibling of the main exe)
#   * the resource/bundle dir itself
#   * its parent (covers older layouts and Linux/Windows AppImage/MSI)
# On Windows-style names we also try the `.exe` variant in each directory,
# mirroring resolve_sidecar. Keep both lists in sync when either changes.
# ---------------------------------------------------------------------------

locate_binary() {
    local name="$1"
    local dir
    local candidate
    # Probe directories, in priority order, matching resolve_sidecar's set.
    # The trailing usr/lib/coffer entry is a Linux deb/AppImage path kept for
    # extracted-archive layouts.
    for dir in \
        "$BUNDLE/Contents/MacOS" \
        "$BUNDLE" \
        "$BUNDLE/.." \
        "$BUNDLE/usr/lib/coffer"; do
        for candidate in "$dir/$name" "$dir/$name.exe"; do
            if [ -f "$candidate" ]; then
                printf '%s\n' "$candidate"
                return 0
            fi
        done
    done
    return 1
}

SHIM="$(locate_binary coffer-mcp-shim || true)"
if [ -z "$SHIM" ]; then
    echo "error: could not locate coffer-mcp-shim in $BUNDLE" >&2
    echo "searched paths:" >&2
    find "$BUNDLE" -name 'coffer-mcp-shim*' 2>/dev/null | head -20 >&2 || true
    exit 2
fi

# Locate the daemon: explicit arg wins, else probe next to the shim.
if [ -n "$DAEMON_ARG" ]; then
    DAEMON="$DAEMON_ARG"
else
    DAEMON="$(locate_binary coffer-daemon || true)"
fi
if [ -z "$DAEMON" ] || [ ! -f "$DAEMON" ]; then
    echo "error: could not locate coffer-daemon in $BUNDLE" >&2
    echo "searched paths:" >&2
    find "$BUNDLE" -name 'coffer-daemon*' 2>/dev/null | head -20 >&2 || true
    exit 2
fi

# Make sure the binaries are executable (they always should be in a proper
# bundle, but re-applying chmod is harmless and avoids confusing "permission
# denied" failures when running against an extracted archive on some CI
# systems).
chmod +x "$SHIM" "$DAEMON" 2>/dev/null || true

echo "==> smoke-testing shim:   $SHIM"
echo "==> smoke-testing daemon: $DAEMON"

# ---------------------------------------------------------------------------
# Isolated sandbox — use a temp dir as HOME so we don't read/write the
# developer's real ~/.coffer state during the test.
# ---------------------------------------------------------------------------

SMOKE_HOME="$(mktemp -d -t coffer-smoke-XXXXXX)"
# Use mktemp for the stderr capture too — a predictable /tmp path is racy
# (two concurrent smoke tests would clobber each other's diagnostics) and
# tempts symlink games on shared CI runners.
SMOKE_STDERR="$(mktemp -t coffer-smoke-stderr-XXXXXX)"
DAEMON_STDERR="$(mktemp -t coffer-smoke-daemon-XXXXXX)"
SHIM_OUT="$(mktemp -t coffer-smoke-out-XXXXXX)"
DAEMON_PID=""
SHIM_PID=""

cleanup() {
    if [ -n "$SHIM_PID" ] && kill -0 "$SHIM_PID" 2>/dev/null; then
        kill "$SHIM_PID" 2>/dev/null || true
    fi
    if [ -n "$DAEMON_PID" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
        kill "$DAEMON_PID" 2>/dev/null || true
        # Give it a moment, then force.
        for _ in 1 2 3 4 5; do
            kill -0 "$DAEMON_PID" 2>/dev/null || break
            sleep 0.3
        done
        kill -9 "$DAEMON_PID" 2>/dev/null || true
    fi
    rm -rf "$SMOKE_HOME" "$SMOKE_STDERR" "$DAEMON_STDERR" "$SHIM_OUT"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Step 1: Start the bundled daemon under the isolated HOME and wait until it
# is listening. The shim only replies once it reaches a live daemon; its
# frozen-binary auto-spawn fallback can't relaunch itself, so we start it.
# ---------------------------------------------------------------------------

DAEMON_JSON="$SMOKE_HOME/.coffer/daemon.json"

echo "==> starting daemon under HOME=$SMOKE_HOME"
HOME="$SMOKE_HOME" "$DAEMON" >"$DAEMON_STDERR" 2>&1 &
DAEMON_PID=$!

# Wait (up to 30s) for the daemon to publish daemon.json and answer /status.
# The port in daemon.json doesn't change once written, so parse it exactly
# once (the first time the file appears) instead of re-forking python3 on
# every poll iteration — afterwards the loop only re-issues the cheap curl
# health check.
DAEMON_READY=0
PORT=""
_elapsed=0
while [ "$_elapsed" -lt 30 ]; do
    if ! kill -0 "$DAEMON_PID" 2>/dev/null; then
        echo "FAIL: daemon process exited before becoming ready" >&2
        echo "==> daemon output:" >&2
        cat "$DAEMON_STDERR" >&2 || true
        exit 6
    fi
    if [ -z "$PORT" ] && [ -f "$DAEMON_JSON" ]; then
        PORT="$(
            HOME="$SMOKE_HOME" python3 -c \
                "import json;print(json.load(open(r'$DAEMON_JSON')).get('port',''))" \
                2>/dev/null || true
        )"
    fi
    if [ -n "$PORT" ] && \
       curl -sf "http://127.0.0.1:$PORT/api/v1/daemon/status" >/dev/null 2>&1; then
        DAEMON_READY=1
        break
    fi
    sleep 1
    _elapsed=$((_elapsed + 1))
done

if [ "$DAEMON_READY" -ne 1 ]; then
    echo "FAIL: daemon did not become ready within 30 s" >&2
    echo "==> daemon output:" >&2
    cat "$DAEMON_STDERR" >&2 || true
    exit 6
fi

echo "==> daemon ready on port $PORT"

# ---------------------------------------------------------------------------
# Step 2: Shim JSON-RPC initialize
#
# Send a minimal MCP initialize request and capture the first output line.
# The shim is expected to reply with a JSON-RPC 2.0 response on stdout.
# ---------------------------------------------------------------------------

INPUT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

echo "==> sending: $INPUT"

# Run the shim with a 15-second watchdog to guard against hangs. Two macOS
# pitfalls drove this design:
#   1. No `timeout`: it's GNU coreutils, absent on macOS by default (and named
#      `gtimeout` when brew-installed), so a `timeout`-based guard fails the
#      macOS release leg. We background the shim and poll instead.
#   2. The shim's stdin MUST be a pipe, not a regular file: its asyncio
#      `_pump_stdin` calls `connect_read_pipe`, which raises "Pipe transport is
#      for pipes/sockets only" on a regular file. A bash here-doc is delivered
#      as a temp *file* on macOS (bash 3.2) but as a *pipe* on Linux (bash 5.x)
#      — which is exactly why the heredoc form passed on Linux yet failed on
#      macOS. Process substitution `< <(...)` is a real pipe on both. (Real MCP
#      clients always pipe the shim's stdin, so this only bit the test harness.)
# printf exits after one line, EOF-ing the pipe so the shim replies and exits.
HOME="$SMOKE_HOME" "$SHIM" >"$SHIM_OUT" 2>"$SMOKE_STDERR" < <(printf '%s\n' "$INPUT") &
SHIM_PID=$!

_w=0
while [ "$_w" -lt 15 ]; do
    [ -s "$SHIM_OUT" ] && break
    kill -0 "$SHIM_PID" 2>/dev/null || break  # shim exited (output already flushed)
    sleep 1
    _w=$((_w + 1))
done
if kill -0 "$SHIM_PID" 2>/dev/null; then
    kill "$SHIM_PID" 2>/dev/null || true
fi
wait "$SHIM_PID" 2>/dev/null || true
SHIM_PID=""
REPLY="$(head -1 "$SHIM_OUT" 2>/dev/null || true)"

# Show any stderr output for diagnostics (don't fail on empty).
if [ -s "$SMOKE_STDERR" ]; then
    echo "==> shim stderr:"
    cat "$SMOKE_STDERR" >&2
fi

if [ -z "$REPLY" ]; then
    echo "FAIL: no reply from shim within 15 s" >&2
    exit 3
fi

echo "==> reply: $REPLY"

# ---------------------------------------------------------------------------
# Step 3: Validate the reply is a proper JSON-RPC 2.0 response with id=1.
#
# The shim emits JSON via json.dumps with default separators, so the wire
# form is spaced (`"jsonrpc": "2.0", "id": 1`). Match whitespace-tolerantly
# so both compact and spaced encodings pass.
# ---------------------------------------------------------------------------

if ! printf '%s' "$REPLY" | grep -Eq '"jsonrpc"[[:space:]]*:[[:space:]]*"2\.0"'; then
    echo 'FAIL: reply missing "jsonrpc": "2.0"' >&2
    exit 4
fi

if ! printf '%s' "$REPLY" | grep -Eq '"id"[[:space:]]*:[[:space:]]*1'; then
    echo 'FAIL: reply does not contain "id": 1' >&2
    exit 5
fi

# ---------------------------------------------------------------------------
# All checks passed
# ---------------------------------------------------------------------------

echo ""
echo "smoke test PASSED"
echo "  shim   : $SHIM"
echo "  daemon : $DAEMON"
echo "  reply  : $REPLY"
exit 0
