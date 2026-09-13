//! The four IPC commands the webview calls, and the detect-or-spawn policy
//! behind them.
//!
//! Where a daemon comes from lives in `resolve.rs` (the five-step chain);
//! reading `daemon.json` and probing a port lives in `discovery.rs`; starting
//! one lives in `spawn.rs`. This file owns only the policy: rate limiting,
//! stop-then-start, and the credential handshake.

use tauri::AppHandle;

use crate::discovery::{
    daemon_responds_ok, read_daemon_info, request_daemon_shutdown, wait_for_port_free,
};
use crate::resolve::{daemon_source, DaemonSource};
use crate::spawn::spawn_resolved_daemon;

#[derive(serde::Serialize)]
pub struct RestartResult {
    pub pid: u32,
    pub started: bool,
}

/// Rate-limit state for `restart_daemon`. We refuse calls that arrive less
/// than `RESTART_MIN_INTERVAL_SECS` after the last successful restart, to
/// avoid an accidental tight-loop spawning many daemon processes.
static LAST_RESTART_AT: std::sync::Mutex<Option<std::time::Instant>> = std::sync::Mutex::new(None);
const RESTART_MIN_INTERVAL_SECS: u64 = 5;

/// Pure rate-limit decision for `restart_daemon`, split out so it can be
/// unit-tested without spawning processes. Returns `true` when `now` is less
/// than `min_interval` after the previous restart (so the call is refused).
fn restart_is_rate_limited(
    prev: Option<std::time::Instant>,
    now: std::time::Instant,
    min_interval: std::time::Duration,
) -> bool {
    match prev {
        Some(p) => now.duration_since(p) < min_interval,
        None => false,
    }
}

/// Restart the daemon: stop the running one (if any), spawn a fresh one.
///
/// Behaviour:
///   1. Rate-limit: refuse if called within `RESTART_MIN_INTERVAL_SECS` of
///      the previous successful restart.
///   2. True restart: if `~/.coffer/daemon.json` lists a responsive daemon,
///      POST its token-gated /daemon/shutdown route and wait for the port
///      to free.
///   3. Resolve (five-step chain) and spawn detached; return the PID.
#[tauri::command]
pub fn restart_daemon(app: AppHandle) -> Result<RestartResult, String> {
    use std::time::{Duration, Instant};

    // Hold the rate-limit mutex across the ENTIRE operation (check + stop +
    // spawn + timestamp record). This intentionally serializes concurrent
    // `restart_daemon` calls so the second caller sees either the
    // just-recorded timestamp (→ rate-limited) or the now-running daemon,
    // closing the double-spawn race. The blocking TCP probe (~250ms) + spawn
    // happen under the lock; that's acceptable for a rare, user-initiated
    // manual restart.
    let mut guard = LAST_RESTART_AT
        .lock()
        .map_err(|e| format!("restart lock poisoned: {e}"))?;

    // (1) Rate-limit guard. We only CHECK here against the last *successful*
    // spawn — we do NOT record `now` yet. The timestamp is recorded only
    // after we actually spawn a new daemon (see step 3), so a failed spawn
    // does not consume the rate-limit window and the user can retry at once.
    {
        let now = Instant::now();
        let min_interval = Duration::from_secs(RESTART_MIN_INTERVAL_SECS);
        if restart_is_rate_limited(*guard, now, min_interval) {
            let elapsed = now.duration_since(guard.expect("rate-limited implies a prior restart"));
            let remaining = RESTART_MIN_INTERVAL_SECS - elapsed.as_secs();
            return Err(format!(
                "restart_daemon: rate-limited; retry in {}s",
                remaining.max(1)
            ));
        }
    }

    // (2) True restart: when a daemon is responsive, ask it to shut down
    // (token-gated POST /daemon/shutdown) and wait for the port to free
    // before spawning the replacement. A silent no-op here would mean
    // "Restart daemon" did nothing exactly when a user reaches for it (a
    // wedged-but-listening daemon).
    if let Some((port, token)) = read_daemon_info() {
        if daemon_responds_ok(port) {
            request_daemon_shutdown(port, &token)?;
            if !wait_for_port_free(port, Duration::from_secs(8)) {
                return Err(format!(
                    "daemon on port {port} did not stop within 8s of the shutdown request"
                ));
            }
            log::info!("daemon on port {} stopped for restart", port);
        }
    }

    // (3) Resolve + spawn detached.
    let pid = spawn_resolved_daemon(&app)?;

    // Record the rate-limit timestamp ONLY now — after a successful spawn —
    // so the window is never consumed by a failed one. We still hold the
    // guard acquired at the top of the function.
    *guard = Some(Instant::now());

    log::info!("daemon restarted (pid {})", pid);
    Ok(RestartResult { pid, started: true })
}

/// The version this app build expects the daemon to report. Sourced from the
/// crate version (`Cargo.toml`) at compile time, never a hardcoded literal —
/// so a freshly-installed app and an old detached daemon it reuses cannot
/// silently disagree.
pub const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Whether a running daemon's reported `version` is compatible with the
/// version this app build `expected`. Pure so it's unit-testable.
///
/// Compatibility is exact string match: the app and the daemon it bundles
/// ship together, so any difference means the app is talking to a stale
/// daemon (typically one a previous app version left detached and listening).
/// An empty/absent daemon version is treated as a mismatch — we can't confirm
/// it matches, so we surface the "restart it" affordance rather than assume.
pub fn version_is_compatible(expected: &str, daemon: &str) -> bool {
    !daemon.is_empty() && expected == daemon
}

/// Expose this app build's expected daemon version to the web UI (shown in the
/// version-skew banner copy so the user sees what the app expected).
#[tauri::command]
pub fn get_app_version() -> String {
    APP_VERSION.to_string()
}

/// Whether the running daemon's reported version matches what this app build
/// expects. The web UI passes the `version` from `/api/v1/daemon/status`; on
/// `false` it surfaces a "daemon out of date — restart it" banner (reusing the
/// existing restart affordance rather than auto-killing the daemon). The
/// comparison lives here so the single source of truth for "compatible" is the
/// app build's own `APP_VERSION`, not a literal duplicated in the frontend.
#[tauri::command]
pub fn daemon_version_matches(daemon_version: String) -> bool {
    version_is_compatible(APP_VERSION, &daemon_version)
}

/// Daemon connection info handed to the web UI inside the desktop app.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DaemonInfo {
    /// `http://127.0.0.1:<port>/api/v1`
    pub base_url: String,
    pub token: String,
}

/// Return the running daemon's base URL + token for the webview to
/// authenticate with.
///
/// The desktop app loads the frontend as a bundled static asset, so no daemon
/// injected a token into the document the way it does for a browser. The page
/// calls this on startup and sets `window.__COFFER_TOKEN__` /
/// `__COFFER_BASE_URL__` before any API request.
///
/// Detect-or-spawn runs through the five-step chain: a daemon we can take over
/// is reused as-is; otherwise we spawn the binary the chain found and wait (up
/// to ~15s) for it to publish `daemon.json` and answer.
#[tauri::command]
pub fn get_daemon_info(app: AppHandle) -> Result<DaemonInfo, String> {
    use std::thread::sleep;
    use std::time::{Duration, Instant};

    let ready = |port: u16, token: String| DaemonInfo {
        base_url: format!("http://127.0.0.1:{port}/api/v1"),
        token,
    };

    // Step 1 of the chain short-circuits the whole cold start.
    if let DaemonSource::Running { port, token } = daemon_source(&app)? {
        return Ok(ready(port, token));
    }

    // Cold start: spawn the resolved binary, then poll until it answers.
    spawn_resolved_daemon(&app)?;
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if let Some((port, token)) = read_daemon_info() {
            if daemon_responds_ok(port) {
                return Ok(ready(port, token));
            }
        }
        sleep(Duration::from_millis(250));
    }
    Err("coffer-daemon did not become ready within 15s".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    #[test]
    fn rate_limited_within_interval() {
        let prev = Instant::now();
        let now = prev + Duration::from_secs(2);
        assert!(restart_is_rate_limited(
            Some(prev),
            now,
            Duration::from_secs(5)
        ));
    }

    #[test]
    fn not_rate_limited_after_interval() {
        let prev = Instant::now();
        let now = prev + Duration::from_secs(6);
        assert!(!restart_is_rate_limited(
            Some(prev),
            now,
            Duration::from_secs(5)
        ));
    }

    #[test]
    fn not_rate_limited_on_first_call() {
        assert!(!restart_is_rate_limited(
            None,
            Instant::now(),
            Duration::from_secs(5)
        ));
    }

    // --- version skew: the app must detect when it has reused an old
    // detached daemon whose reported version differs from what this build
    // expects, so it can surface a manual "restart it" prompt. ---

    #[test]
    fn version_is_compatible_when_versions_match() {
        assert!(version_is_compatible("0.1.1", "0.1.1"));
    }

    #[test]
    fn version_is_incompatible_when_daemon_is_older() {
        // The classic skew: a new app build reuses a daemon a previous app
        // version left running.
        assert!(!version_is_compatible("0.1.1", "0.1.0"));
    }

    #[test]
    fn version_is_incompatible_when_daemon_is_newer() {
        assert!(!version_is_compatible("0.1.1", "0.2.0"));
    }

    #[test]
    fn version_is_incompatible_when_daemon_version_is_empty() {
        // A daemon that didn't report a version can't be confirmed current —
        // treat it as a mismatch so the affordance still shows.
        assert!(!version_is_compatible("0.1.1", ""));
    }

    #[test]
    fn get_app_version_returns_the_crate_version() {
        // Sourced from CARGO_PKG_VERSION, not a hardcoded literal.
        assert_eq!(get_app_version(), env!("CARGO_PKG_VERSION"));
        assert!(!get_app_version().is_empty());
    }

    #[test]
    fn daemon_version_matches_compares_against_this_app_build() {
        // The command the web UI calls: true only when the daemon reports
        // exactly this build's version.
        assert!(daemon_version_matches(APP_VERSION.to_string()));
        assert!(!daemon_version_matches("0.0.0-stale".to_string()));
        assert!(!daemon_version_matches(String::new()));
    }
}
