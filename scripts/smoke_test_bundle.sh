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
#   1. Locate coffer-mcp-shim (and optionally coffer-daemon) inside the bundle.
#   2. Spawn the shim with an isolated HOME, send one JSON-RPC 2.0 "initialize"
#      request over stdin, and assert a well-formed reply comes back within 15 s.
#   3. Exit 0 on success; non-zero with diagnostics on failure.
#
# The test does NOT start the full Tauri GUI — it exercises the sidecar binaries
# directly.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

BUNDLE="${1:?usage: $0 <bundle-path>}"

if [ ! -d "$BUNDLE" ] && [ ! -f "$BUNDLE" ]; then
    echo "error: bundle path does not exist: $BUNDLE" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate coffer-mcp-shim
# ---------------------------------------------------------------------------

SHIM=""
for candidate in \
    "$BUNDLE/Contents/MacOS/coffer-mcp-shim" \
    "$BUNDLE/Contents/Resources/coffer-mcp-shim" \
    "$BUNDLE/coffer-mcp-shim" \
    "$BUNDLE/usr/lib/coffer/coffer-mcp-shim" \
    "$BUNDLE/coffer-mcp-shim.exe"; do
    if [ -f "$candidate" ]; then
        SHIM="$candidate"
        break
    fi
done

if [ -z "$SHIM" ]; then
    echo "error: could not locate coffer-mcp-shim in $BUNDLE" >&2
    echo "searched paths:" >&2
    find "$BUNDLE" -name 'coffer-mcp-shim*' 2>/dev/null | head -20 >&2 || true
    exit 2
fi

# Make sure the binary is executable (it always should be in a proper bundle,
# but re-applying chmod is harmless and avoids confusing "permission denied"
# failures when running against an extracted archive on some CI systems).
chmod +x "$SHIM" 2>/dev/null || true

echo "==> smoke-testing shim: $SHIM"

# ---------------------------------------------------------------------------
# Isolated sandbox — use a temp dir as HOME so we don't read/write the
# developer's real ~/.coffer state during the test.
# ---------------------------------------------------------------------------

SMOKE_HOME="$(mktemp -d -t coffer-smoke-XXXXXX)"
# Use mktemp for the stderr capture too — a predictable /tmp path is racy
# (two concurrent smoke tests would clobber each other's diagnostics) and
# tempts symlink games on shared CI runners.
SMOKE_STDERR="$(mktemp -t coffer-smoke-stderr-XXXXXX)"
trap 'rm -rf "$SMOKE_HOME" "$SMOKE_STDERR"' EXIT

# ---------------------------------------------------------------------------
# Step 1: Shim JSON-RPC initialize
#
# Send a minimal MCP initialize request and capture the first output line.
# The shim is expected to reply with a JSON-RPC 2.0 response on stdout.
# ---------------------------------------------------------------------------

INPUT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'

echo "==> sending: $INPUT"

# Run the shim under a 15-second timeout to guard against hangs.
# We feed the JSON-RPC request via heredoc (process-substitution would also
# work) rather than embedding it in a single-quoted `bash -c` string — the
# old form broke any time the payload contained a literal single quote.
REPLY=$(
    HOME="$SMOKE_HOME" timeout 15 "$SHIM" 2>"$SMOKE_STDERR" <<EOF | head -1 || true
$INPUT
EOF
)

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
# Step 2: Validate the reply is a proper JSON-RPC 2.0 response with id=1
# ---------------------------------------------------------------------------

if ! printf '%s' "$REPLY" | grep -q '"jsonrpc":"2.0"'; then
    echo 'FAIL: reply missing "jsonrpc":"2.0"' >&2
    exit 4
fi

if ! printf '%s' "$REPLY" | grep -q '"id":1'; then
    echo 'FAIL: reply does not contain "id":1' >&2
    exit 5
fi

# ---------------------------------------------------------------------------
# All checks passed
# ---------------------------------------------------------------------------

echo ""
echo "smoke test PASSED"
echo "  shim   : $SHIM"
echo "  reply  : $REPLY"
exit 0
