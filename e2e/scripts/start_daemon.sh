#!/usr/bin/env bash
# Start a coffer daemon with an isolated HOME for the e2e suite.
# Playwright's webServer will poll /api/v1/daemon/status until 200 OK.
set -euo pipefail

# Create a per-run isolated dir (or reuse one passed in via env)
COFFER_E2E_HOME="${COFFER_E2E_HOME:-$(mktemp -d -t coffer-e2e-XXXXXX)}"
export HOME="${COFFER_E2E_HOME}"
export COFFER_DB_URL="sqlite+aiosqlite:///${COFFER_E2E_HOME}/coffer.db"
export COFFER_PORT_RANGE_START=18000
export COFFER_PORT_RANGE_END=18009

# Make sure the .coffer dir exists so daemon bootstrap can write daemon.json
mkdir -p "${COFFER_E2E_HOME}/.coffer"

# Persist the chosen home path so _helpers.ts can locate daemon.json
echo "${COFFER_E2E_HOME}" > "/tmp/coffer-e2e-home.path"

# Wait up to 45 s for port 18000 to be truly free (handles TCP TIME_WAIT).
# macOS TIME_WAIT is 2 * net.inet.tcp.msl = 2 * 15 s = 30 s.
# We intentionally do NOT use SO_REUSEADDR here — the daemon's port allocator
# does not set SO_REUSEADDR, so we need the port to be clean before we start.
WAIT_PORT=18000
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
exec "${VENV_PYTHON}" -m coffer.infrastructure.daemon.entry
