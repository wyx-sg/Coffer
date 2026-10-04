#!/usr/bin/env bash
# smoke_test_bundle.sh — Verify the binaries in a built Coffer CLI archive.
#
# Usage:
#   ./scripts/smoke_test_bundle.sh <path-to-binaries-dir>
#
# Point it at a directory holding the plain-named binaries: the `dist/`
# directory build_binaries.sh writes, or a directory extracted from a
# released coffer-cli-<triple>.tar.gz.
#
# What it does:
#   1. Locate coffer, coffer-mcp-shim AND coffer-daemon inside the bundle.
#   2. Start the bundled coffer-daemon under an isolated HOME, on a free port
#      of its own, and wait until it has published ~/.coffer/daemon.json and is
#      answering /daemon/status.
#   3. Ask that daemon for its root and assert it serves the bundled web UI.
#   4. Run the bundled CLI's `coffer daemon status` against it.
#   5. Spawn the shim with the SAME isolated HOME, send one JSON-RPC 2.0
#      "initialize" request over stdin, and assert a well-formed reply comes
#      back within 15 s — exercising the real shim -> daemon /mcp round-trip.
#   6. Tear the daemon and its model proxy down and exit 0 on success;
#      non-zero with diagnostics on failure.
#
# The shim only replies once it reaches a live coffer-daemon, and its
# auto-spawn fallback (sys.executable -m ...) does NOT work inside a frozen
# PyInstaller binary — so this script starts the bundled daemon itself rather
# than relying on that fallback.
#
# An explicit daemon path may be passed as the second argument; otherwise it
# is probed next to the shim.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

BUNDLE="${1:?usage: $0 <binaries-dir> [daemon-path]}"
DAEMON_ARG="${2:-}"

if [ ! -d "$BUNDLE" ]; then
    echo "error: binaries directory does not exist: $BUNDLE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate a binary by name in the archive directory. The CLI archive ships every
# binary co-located under its plain name (no triple suffix) — that co-location
# is what the frozen detect-or-spawn logic relies on at runtime (ADR daemon-detect-or-spawn), so
# probing a single directory is exactly the layout under test. The `.exe`
# variant is tried too for Windows-style extractions.
# ---------------------------------------------------------------------------

locate_binary() {
    local name="$1"
    local candidate
    for candidate in "$BUNDLE/$name" "$BUNDLE/$name.exe"; do
        if [ -f "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
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
CLI="$(locate_binary coffer || true)"
if [ -z "$CLI" ]; then
    echo "error: could not locate coffer (the CLI) in $BUNDLE" >&2
    exit 2
fi

chmod +x "$SHIM" "$DAEMON" "$CLI" 2>/dev/null || true

echo "==> smoke-testing shim:   $SHIM"
echo "==> smoke-testing daemon: $DAEMON"
echo "==> smoke-testing cli:    $CLI"

# ---------------------------------------------------------------------------
# Isolated sandbox — use a temp dir as HOME so we don't read/write the
# developer's real ~/.coffer state during the test.
#
# The isolation is only as good as what the daemon itself scopes to HOME. It
# was once not enough: the daemon's startup reaper matched sibling daemons by
# executable name alone, so the daemon started here terminated the developer's
# live one. It now requires the same vault (orphan_sweep.reap_stale_daemons),
# which is what makes this script safe to run on a working machine.
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
SMOKE_PROXY_PORT=""

# The daemon starts the local model proxy as a separate process that outlives
# it by design (it serves the agents' configured base URL across daemon
# restarts), so stopping the daemon leaves it running. It records its pid in
# the isolated home; stop it only if that pid is still a proxy on the port
# this run chose for it (the daemon spawns it by its resolved absolute path, so
# the port, not the path, is what identifies it).
stop_proxy() {
    local proxy_json="$SMOKE_HOME/.coffer/proxy.json" pid
    [ -f "$proxy_json" ] || return 0
    pid="$(python3 -c "import json;print(json.load(open(r'$proxy_json')).get('pid',''))" 2>/dev/null || true)"
    [ -n "$pid" ] || return 0
    case "$(ps -o command= -p "$pid" 2>/dev/null || true)" in
        *"coffer-daemon proxy --port $SMOKE_PROXY_PORT") kill "$pid" 2>/dev/null || true ;;
    esac
}

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
    stop_proxy
    rm -rf "$SMOKE_HOME" "$SMOKE_STDERR" "$DAEMON_STDERR" "$SHIM_OUT"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Step 1: Start the bundled daemon under the isolated HOME and wait until it
# is listening. The shim only replies once it reaches a live daemon; its
# frozen-binary auto-spawn fallback can't relaunch itself, so we start it.
# ---------------------------------------------------------------------------

DAEMON_JSON="$SMOKE_HOME/.coffer/daemon.json"

# Pin free ports for the daemon and its model proxy. Without a setting the
# daemon insists on 38470 and the proxy on 38471, so on a machine that already
# runs Coffer — any developer's, where this script is also meant to run — the
# bundled daemon cannot bind and the test fails for a reason that has nothing
# to do with the bundle. The ports go in daemon-config.json, the one place the
# daemon reads them from before it binds.
read -r SMOKE_PORT SMOKE_PROXY_PORT < <(python3 -c '
import socket
socks = [socket.socket() for _ in range(2)]
for s in socks:
    s.bind(("127.0.0.1", 0))
print(*(s.getsockname()[1] for s in socks))
for s in socks:
    s.close()
')
mkdir -p "$SMOKE_HOME/.coffer"
chmod 700 "$SMOKE_HOME/.coffer"
printf '{"port": %s, "proxy_port": %s}\n' "$SMOKE_PORT" "$SMOKE_PROXY_PORT" \
    >"$SMOKE_HOME/.coffer/daemon-config.json"

# Give the isolated home its own development master key. The daemon looks for
# the key file first and, finding none, asks the login keychain — which is not
# scoped to HOME, so on a developer's machine the smoke daemon would read (and
# may prompt for) that person's real Coffer key.
python3 -c '
import base64, os, sys
path = sys.argv[1]
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd, base64.urlsafe_b64encode(os.urandom(32)))
os.close(fd)
' "$SMOKE_HOME/.coffer/master.key"

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
if [ "$PORT" != "$SMOKE_PORT" ]; then
    echo "FAIL: daemon bound $PORT, not the configured $SMOKE_PORT" >&2
    exit 6
fi

# ---------------------------------------------------------------------------
# Step 1b: the bundled web UI
#
# `coffer-daemon.spec` folds `frontend/dist` in as `webui/` ONLY when
# `index.html` is already sitting there at build time — build the binaries
# without building the frontend first and PyInstaller silently produces a
# daemon that serves an API and no interface. Nothing about that build fails,
# and `--version` and /daemon/status both look perfectly healthy, so the smoke
# test is the one place it can be caught before a release ships it.
#
# Asking the RUNNING daemon for its root and requiring a hashed asset
# reference proves the whole path: the data files made it into the archive,
# `webui.resolve_webui_dir()` found them inside the bundle, and the route
# serves them. A bare "200 with some HTML" would not — the not-found page is
# also HTML.
#
# (This step used to assert `vec_available` on /daemon/status, which the
# daemon no longer reports: sqlite-vec went away with the retrieval index,
# and `sqlite_vec` is now on the banned-import list in backend/pyproject.toml.
# The assertion could never pass again, so every healthy build failed here.)
# ---------------------------------------------------------------------------

echo "==> checking the daemon serves the bundled web UI"
INDEX_HTML="$(curl -sf "http://127.0.0.1:$PORT/" 2>&1)" || {
    echo "FAIL: the bundled daemon does not serve the web UI at /" >&2
    echo "      (the frozen build has no webui/ — was frontend/dist built" >&2
    echo "       before the binaries? see backend/coffer-daemon.spec)" >&2
    exit 7
}
case "$INDEX_HTML" in
    *'assets/index-'*) echo "==> web UI served (hashed asset referenced)" ;;
    *)
        echo "FAIL: / returned no hashed asset reference — the bundled UI is" >&2
        echo "      missing or stale. Got:" >&2
        printf '%s\n' "$INDEX_HTML" | head -20 >&2
        exit 7
        ;;
esac

# ---------------------------------------------------------------------------
# Step 1c: the bundled CLI
#
# The CLI is frozen from its own spec with its own excludes, and none of the
# steps above run it — a CLI that cannot import at all (as happened when
# coffer.spec excluded a package `coffer migrate` imports at start) shipped
# with every other check green. `coffer daemon status` imports the whole
# command tree and talks to the daemon started above.
# ---------------------------------------------------------------------------

echo "==> checking the bundled CLI reaches the daemon"
CLI_OUT="$(HOME="$SMOKE_HOME" "$CLI" daemon status 2>&1)" || {
    echo "FAIL: \`coffer daemon status\` failed:" >&2
    printf '%s\n' "$CLI_OUT" >&2
    exit 8
}
case "$CLI_OUT" in
    *ready*) echo "==> cli: daemon status ready" ;;
    *)
        echo "FAIL: \`coffer daemon status\` did not report a ready daemon:" >&2
        printf '%s\n' "$CLI_OUT" >&2
        exit 8
        ;;
esac

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
