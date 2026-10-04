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
    wait_until_ready(
        deadline,
        read_daemon_info,
        daemon_responds_ok,
        std::thread::sleep,
    )
}

/// [`wait_for_daemon_ready`] with its three side effects injected, so the
/// sequencing is testable without a socket or a clock.
///
/// `read` is called afresh on every poll: after a restart that changed the
/// daemon's port, the file first names the stopped daemon's port (nothing
/// answers there) and then, once the replacement has bound, the new one. The
/// connection returned is whatever the file names when something answers — the
/// port is never carried over from before the restart (spec desktop-app
/// "Restart by stopping the running daemon first").
fn wait_until_ready<R, P, S>(
    deadline: std::time::Instant,
    mut read: R,
    mut responds: P,
    mut sleep: S,
) -> Option<(u16, String)>
where
    R: FnMut() -> Option<(u16, String)>,
    P: FnMut(u16) -> bool,
    S: FnMut(std::time::Duration),
{
    use std::time::{Duration, Instant};
    loop {
        if let Some((port, token)) = read() {
            if responds(port) {
                return Some((port, token));
            }
        }
        if Instant::now() >= deadline {
            return None;
        }
        sleep(Duration::from_millis(DAEMON_READY_POLL_MS));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    use std::time::{Duration, Instant};

    // acceptance(spec = "desktop-app", scenario = "a restart onto a changed port reconnects the shell to the new port")
    #[test]
    fn a_restart_onto_a_new_port_hands_back_the_new_port_and_token() {
        // The file still names the stopped daemon on the first polls, then the
        // replacement on the port the user saved in Settings -> Daemon.
        let polls = Cell::new(0u32);
        let read = || {
            polls.set(polls.get() + 1);
            if polls.get() < 3 {
                Some((38470, "old-token".to_string()))
            } else {
                Some((39001, "new-token".to_string()))
            }
        };
        let responds = |port: u16| port == 39001;
        let got = wait_until_ready(
            Instant::now() + Duration::from_secs(60),
            read,
            responds,
            |_| {},
        );
        assert_eq!(got, Some((39001, "new-token".to_string())));
        assert_eq!(base_url_for(39001), "http://127.0.0.1:39001/api/v1");
    }

    #[test]
    fn a_daemon_that_never_answers_is_given_up_on_at_the_deadline() {
        let got = wait_until_ready(
            Instant::now(),
            || Some((38470, "tok".to_string())),
            |_| false,
            |_| {},
        );
        assert_eq!(got, None);
    }
}
