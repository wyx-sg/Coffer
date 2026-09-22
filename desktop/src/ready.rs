//! When a daemon the shell started counts as ready, and how long it is given.
//!
//! Split out of `daemon.rs` to keep every file under the project's 400-line
//! cap (see `.agents/stack.md`). Both IPC commands that can start a daemon —
//! the launch handshake and the restart — wait through here, so the budget
//! and the probe are one decision rather than two that can drift.

use crate::discovery::{daemon_responds_ok, read_daemon_info};

/// How long a daemon the shell just started is given to answer before the
/// shell calls it a failure.
///
/// It is a ceiling, not an expectation. A daemon does not serve the moment it
/// is spawned: the frozen binary unpacks itself, migrations run, the MCP
/// upstreams and channel listeners come up in the FastAPI lifespan, and only
/// then does uvicorn accept. On a real vault that takes anywhere from five to
/// fifteen seconds, and longer when a remote upstream is slow to answer — the
/// previous fifteen-second ceiling sat *inside* that spread, so a launch that
/// landed on the slow end declared a daemon dead while it was seconds from
/// serving. The value now sits well clear of it; the page retries anyway
/// (`credentialDesktopHost`), so this bound only decides how long one attempt
/// waits, never whether the app recovers.
pub const DAEMON_READY_TIMEOUT_SECS: u64 = 90;

/// How often the ready-wait re-probes. Short enough that a daemon that comes
/// up fast is picked up straight away, long enough not to busy-spin.
pub const DAEMON_READY_POLL_MS: u64 = 250;

/// The instant a ready-wait started now should give up at.
pub fn ready_deadline() -> std::time::Instant {
    std::time::Instant::now() + std::time::Duration::from_secs(DAEMON_READY_TIMEOUT_SECS)
}

/// The base URL the webview calls a daemon on `port` at.
pub fn base_url_for(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/v1")
}

/// Poll `~/.coffer/daemon.json` + the status route until a daemon answers, or
/// `deadline` passes. Returns its port and token.
///
/// Both halves matter and neither is enough alone: the file appears when the
/// port is bound, which is *before* the app is serving, so a reader that
/// trusted the file would hand the page a token for a socket that does not
/// answer yet.
pub fn wait_for_daemon_ready(deadline: std::time::Instant) -> Option<(u16, String)> {
    use std::thread::sleep;
    use std::time::{Duration, Instant};
    loop {
        if let Some((port, token)) = read_daemon_info() {
            if daemon_responds_ok(port) {
                return Some((port, token));
            }
        }
        if Instant::now() >= deadline {
            return None;
        }
        sleep(Duration::from_millis(DAEMON_READY_POLL_MS));
    }
}
