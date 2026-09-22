//! The three IPC commands the webview calls, and the detect-or-spawn policy
//! behind them.
//!
//! Where a daemon comes from lives in `resolve.rs` (the five-step chain);
//! reading `daemon.json` and probing a port lives in `discovery.rs`; starting
//! one lives in `spawn.rs`; the pure restart policy — the rate-limit window
//! and the stop-then-start sequence — lives in `restart.rs`. This file owns
//! the commands themselves and the credential handshake.

use tauri::AppHandle;

use crate::discovery::{
    daemon_responds_ok, read_daemon_info, request_daemon_shutdown, wait_for_port_free,
};
use crate::resolve::{daemon_source, DaemonSource};
use crate::restart::{record_restart_outcome, restart_rate_limit_refusal, stop_running_daemon};
use crate::spawn::spawn_resolved_daemon;

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RestartResult {
    pub pid: u32,
    pub started: bool,
    /// The replacement's connection, so the page does not have to ask for one.
    /// Asking again is what used to start a SECOND daemon: the page called
    /// `get_daemon_info` the instant this returned, before the daemon just
    /// spawned had bound a port, and that command's cold-start branch spawned
    /// a rival for it (FR-006/FR-007).
    pub base_url: String,
    pub token: String,
}

/// Rate-limit state for `restart_daemon`. We refuse calls that arrive less
/// than `RESTART_MIN_INTERVAL_SECS` after the last successful restart, to
/// avoid an accidental tight-loop spawning many daemon processes.
static LAST_RESTART_AT: std::sync::Mutex<Option<std::time::Instant>> = std::sync::Mutex::new(None);
const RESTART_MIN_INTERVAL_SECS: u64 = 5;

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
const DAEMON_READY_TIMEOUT_SECS: u64 = 90;

/// How often the ready-wait re-probes. Short enough that a daemon that comes
/// up fast is picked up straight away, long enough not to busy-spin.
const DAEMON_READY_POLL_MS: u64 = 250;

/// Restart the daemon: stop the running one (if any), spawn a fresh one.
///
/// Behaviour:
///   1. Rate-limit: refuse if called within `RESTART_MIN_INTERVAL_SECS` of
///      the previous successful restart.
///   2. True restart: if `~/.coffer/daemon.json` lists a responsive daemon,
///      POST its token-gated /daemon/shutdown route and wait for the port
///      to free.
///   3. Resolve (five-step chain) and spawn detached.
///   4. Wait for the replacement to answer, and return its connection with
///      the PID — the caller installs it rather than handshaking again.
///
/// Declared `async` so the framework runs it off the main thread: steps 2-4
/// block for seconds, and on the main thread that is a frozen window for the
/// whole restart. The tray's own call already spawns a thread for this reason
/// (`tray.rs`); the webview's had no such protection.
#[tauri::command(async)]
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
    if let Some(refusal) = restart_rate_limit_refusal(
        *guard,
        Instant::now(),
        Duration::from_secs(RESTART_MIN_INTERVAL_SECS),
    ) {
        return Err(refusal);
    }

    // (2) True restart: when a daemon is responsive, ask it to shut down
    // (token-gated POST /daemon/shutdown) and wait for the port to free
    // before spawning the replacement. A silent no-op here would mean
    // "Restart daemon" did nothing exactly when a user reaches for it (a
    // wedged-but-listening daemon).
    if let Some(port) = stop_running_daemon(
        read_daemon_info,
        daemon_responds_ok,
        request_daemon_shutdown,
        |port| wait_for_port_free(port, Duration::from_secs(8)),
    )? {
        log::info!("daemon on port {} stopped for restart", port);
    }

    // (3) Resolve + spawn detached. The rate-limit timestamp is recorded ONLY
    // for a spawn that succeeded, so the window is never consumed by a failed
    // one. We still hold the guard acquired at the top of the function.
    let spawned = spawn_resolved_daemon(&app);
    record_restart_outcome(&mut guard, Instant::now(), &spawned);
    let pid = spawned?;

    log::info!("daemon restarted (pid {})", pid);

    // (4) Wait for it to serve, and hand its credentials back. The guard is
    // still held: a second restart arriving mid-wait must queue behind this
    // one rather than shut down the daemon this call is waiting for.
    let Some((port, token)) = wait_for_daemon_ready(ready_deadline()) else {
        let msg = format!(
            "coffer-daemon (pid {pid}) was started but did not answer within {DAEMON_READY_TIMEOUT_SECS}s"
        );
        log::warn!("{msg}");
        return Err(msg);
    };
    log::info!("daemon restarted and serving on port {port} (pid {pid})");
    Ok(RestartResult {
        pid,
        started: true,
        base_url: base_url_for(port),
        token,
    })
}

/// The instant a ready-wait started now should give up at.
fn ready_deadline() -> std::time::Instant {
    std::time::Instant::now() + std::time::Duration::from_secs(DAEMON_READY_TIMEOUT_SECS)
}

/// The base URL the webview calls a daemon on `port` at.
fn base_url_for(port: u16) -> String {
    format!("http://127.0.0.1:{port}/api/v1")
}

/// Poll `~/.coffer/daemon.json` + the status route until a daemon answers, or
/// `deadline` passes. Returns its port and token.
///
/// Both halves matter and neither is enough alone: the file appears when the
/// port is bound, which is *before* the app is serving, so a reader that
/// trusted the file would hand the page a token for a socket that does not
/// answer yet.
fn wait_for_daemon_ready(deadline: std::time::Instant) -> Option<(u16, String)> {
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
/// is reused as-is; otherwise we spawn the binary the chain found and wait
/// (up to [`DAEMON_READY_TIMEOUT_SECS`]) for it to publish `daemon.json` and
/// answer.
///
/// Every outcome is logged (FR-012). It used to be the one thing the shell
/// did silently, and it is the one a user most needs an account of: a
/// handshake that failed here left the page with no API address at all, and
/// nothing in `~/.coffer/logs/daemon.log` said so.
///
/// Declared `async` so the framework runs it off the main thread — the
/// cold-start branch blocks for as long as a daemon takes to boot, and on the
/// main thread that is a frozen window for the whole of it.
#[tauri::command(async)]
pub fn get_daemon_info(app: AppHandle) -> Result<DaemonInfo, String> {
    let ready = |port: u16, token: String| DaemonInfo {
        base_url: base_url_for(port),
        token,
    };

    // Step 1 of the chain short-circuits the whole cold start.
    match daemon_source(&app) {
        Ok(DaemonSource::Running { port, token }) => {
            log::info!("handshake: attached to the daemon serving on port {port}");
            return Ok(ready(port, token));
        }
        Ok(DaemonSource::Binary { .. }) => {}
        Err(e) => {
            log::warn!("handshake: no daemon and none to start: {e}");
            return Err(e);
        }
    }

    // Cold start: spawn the resolved binary, then poll until it answers.
    spawn_resolved_daemon(&app)?;
    match wait_for_daemon_ready(ready_deadline()) {
        Some((port, token)) => {
            log::info!("handshake: spawned daemon is serving on port {port}");
            Ok(ready(port, token))
        }
        None => {
            let msg =
                format!("coffer-daemon did not become ready within {DAEMON_READY_TIMEOUT_SECS}s");
            log::warn!("handshake: {msg}");
            Err(msg)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
    fn app_version_comes_from_the_crate_version() {
        // Sourced from CARGO_PKG_VERSION, not a hardcoded literal — a
        // freshly-installed app and an old detached daemon it reuses cannot
        // silently agree.
        assert_eq!(APP_VERSION, env!("CARGO_PKG_VERSION"));
        assert!(!APP_VERSION.is_empty());
    }

    // --- the readiness budget: a ceiling, not an expectation. ---

    #[test]
    fn the_readiness_budget_clears_a_real_daemon_boot() {
        use std::time::{Duration, Instant};
        // Measured on a real vault: five to fourteen seconds from spawn to
        // serving, and longer when a remote MCP upstream is slow to answer in
        // the lifespan. The previous fifteen-second ceiling sat inside that
        // spread, so a launch that landed on the slow end declared a daemon
        // dead while it was seconds away — and the page had no way back.
        // Pinning it keeps a future "tidy-up" from walking the budget back
        // into the boot times it exists to clear.
        let budget = ready_deadline().saturating_duration_since(Instant::now());
        assert!(
            budget >= Duration::from_secs(60),
            "a budget inside a real daemon's boot time is the bug, not the fix"
        );
    }

    #[test]
    fn the_base_url_is_the_loopback_api_root() {
        // The one address the webview is given, and the only one the CSP
        // admits (`connect-src http://127.0.0.1:*`).
        assert_eq!(base_url_for(8000), "http://127.0.0.1:8000/api/v1");
    }

    /// The ready-wait is what a restart hands its caller a connection from,
    /// and it must give up rather than hang when nothing ever answers.
    // acceptance(spec = "desktop-app", scenario = "a restart hands back the connection it waited for")
    #[test]
    fn the_ready_wait_gives_up_at_its_deadline() {
        use std::time::{Duration, Instant};
        // A deadline already in the past: one probe, then out. Whether that
        // single probe finds this machine's own daemon is not the point —
        // returning at all is, because a wait that never ended would hold the
        // restart (and its lock) open forever.
        let started = Instant::now();
        let _ = wait_for_daemon_ready(Instant::now() - Duration::from_secs(1));
        assert!(started.elapsed() < Duration::from_secs(5));
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
