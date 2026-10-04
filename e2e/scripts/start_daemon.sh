#!/usr/bin/env bash
# Start a coffer daemon with an isolated HOME for the e2e suite.
# Playwright's webServer will poll /api/v1/daemon/status until 200 OK.
set -euo pipefail

# Create a per-run isolated dir (or reuse one passed in via env)
COFFER_E2E_HOME="${COFFER_E2E_HOME:-$(mktemp -d -t coffer-e2e-XXXXXX)}"
export HOME="${COFFER_E2E_HOME}"
export COFFER_DB_URL="sqlite+aiosqlite:///${COFFER_E2E_HOME}/runs.db"
# COFFER_E2E_PORT lets a second suite (the visual baseline,
# playwright.visual.config.ts) run its own daemon beside this one.
COFFER_E2E_PORT="${COFFER_E2E_PORT:-18000}"
export COFFER_PORT_RANGE_START="${COFFER_E2E_PORT}"
export COFFER_PORT_RANGE_END="$((COFFER_E2E_PORT + 9))"
# The browser-driven `web` suite loads the app from the Vite dev server on
# localhost:5173 and calls the daemon cross-origin. The daemon serves the built
# web UI itself, so its CORS allowlist is empty (same-origin) by default and
# every browser fetch would fail with "Failed to fetch".
# COFFER_DEV_CORS=1 adds the Vite dev origins localhost/127.0.0.1:5173.
export COFFER_DEV_CORS=1
# No outbound price-list refresh from a test daemon: tests price from the
# snapshot bundled in the tree.
export COFFER_PRICE_REFRESH=off
# Every experimental feature starts off; the suite's specs drive the pages of
# all four, so the daemon pins them on. COFFER_E2E_FEATURES overrides the pin
# (a spec about a switched-off feature starts its own daemon with it).
export COFFER_FEATURES="${COFFER_E2E_FEATURES:-knowledge=on,memory=on,sync=on,models=on}"

# Make sure the .coffer dir exists so daemon bootstrap can write daemon.json
mkdir -p "${COFFER_E2E_HOME}/.coffer"

# A `bin` directory in the isolated HOME, ahead of everything else on the
# daemon's PATH. Agent detection looks for `claude` / `codex` on every probe, so
# a spec that needs an installed agent on a machine without one (CI) drops a
# stand-in program here and the next detection finds it; nothing is there by
# default, and a real install on the login shell's PATH still comes first.
mkdir -p "${COFFER_E2E_HOME}/bin"
export PATH="${COFFER_E2E_HOME}/bin:${PATH}"

# Persist the chosen home path so _helpers.ts can locate daemon.json.
# COFFER_E2E_HOME_FILE moves the pointer so a second suite does not repoint it.
echo "${COFFER_E2E_HOME}" > "${COFFER_E2E_HOME_FILE:-/tmp/coffer-e2e-home.path}"

# Wait up to 45 s for port 18000 to be truly free (handles TCP TIME_WAIT).
# macOS TIME_WAIT is 2 * net.inet.tcp.msl = 2 * 15 s = 30 s.
# We intentionally do NOT use SO_REUSEADDR here — the daemon's port allocator
# does not set SO_REUSEADDR, so we need the port to be clean before we start.
WAIT_PORT="${COFFER_E2E_PORT}"
WAIT_SECS=45
_waited=0
until /usr/bin/python3 -c "
import socket, sys
s = socket.socket()
try:
    s.bind(('127.0.0.1', ${WAIT_PORT}))
    s.close()
    sys.exit(0)
except OSError:
    s.close()
    sys.exit(1)
" 2>/dev/null; do
  _waited=$((_waited + 1))
  if [ "${_waited}" -ge "${WAIT_SECS}" ]; then
    echo "start_daemon.sh: port ${WAIT_PORT} not free after ${WAIT_SECS}s; proceeding anyway" >&2
    break
  fi
  sleep 1
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# Prefer python3 over the python symlink (which may be a compiled binary on
# some macOS setups rather than a shell wrapper).
VENV_PYTHON="${REPO_ROOT}/.venv/bin/python3"

# Serve THIS checkout's code. `coffer` is installed into the venv editable, so
# `-m coffer...` otherwise resolves to whichever tree the venv was built in —
# and in a git worktree `.venv` is a symlink to the main checkout's, which
# means the daemon under test would be someone else's working copy while every
# assertion in the suite passed. `spawnShim` in e2e/mcp/specs/_helpers.ts sets
# the same variable for the same reason; this is the other half of it.
export PYTHONPATH="${REPO_ROOT}/backend${PYTHONPATH:+:${PYTHONPATH}}"

# Prove it rather than trust it. The failure this guards against is silent and
# green — a suite that tests the wrong tree reports success — so the one thing
# it must not do is keep going when the import lands somewhere unexpected.
RESOLVED="$("${VENV_PYTHON}" -c 'import coffer, pathlib; print(pathlib.Path(coffer.__file__).parent.parent)')"
if [ "${RESOLVED}" != "${REPO_ROOT}/backend" ]; then
  echo "start_daemon.sh: refusing to start — coffer resolves to ${RESOLVED}," >&2
  echo "  not ${REPO_ROOT}/backend. The suite would test a different checkout." >&2
  exit 1
fi

exec "${VENV_PYTHON}" -m coffer.infrastructure.daemon.entry
