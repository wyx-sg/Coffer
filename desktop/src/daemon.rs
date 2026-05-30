//! Daemon-spawn: locate and spawn the bundled `coffer-daemon` binary
//! detached from the Tauri app so it survives app exit.
//!
//! Includes a detect-or-spawn check (skip spawning when a daemon is
//! already listening on the discovery-file port) and a rate-limit guard
//! (refuse rapid repeat calls to avoid runaway process spawning).
//!
//! Split out of `lib.rs` to keep the top-level entry-point file under the
//! project's 400-line cap (see `agents/stack.md`).

use std::env;
use std::fs;
use std::path::PathBuf;

use tauri::AppHandle;

#[derive(serde::Serialize)]
pub struct RestartResult {
    pub pid: u32,
    pub started: bool,
}

/// Rate-limit state for `restart_daemon`. We refuse calls that arrive less
/// than `RESTART_MIN_INTERVAL_SECS` after the last successful restart, to
/// avoid an accidental tight-loop spawning many daemon processes.
static LAST_RESTART_AT: std::sync::Mutex<Option<std::time::Instant>> =
    std::sync::Mutex::new(None);
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

/// Locate the bundled `coffer-daemon` binary in the app's resource directory.
///
/// Thin wrapper over [`crate::shim::resolve_sidecar`], which probes (in order):
/// macOS `Contents/MacOS/`, the resource dir itself, and one level up — also
/// trying the `.exe` variant on Windows.
pub fn bundled_daemon_path(app: &AppHandle) -> Result<PathBuf, String> {
    crate::shim::resolve_sidecar(app, &["coffer-daemon"])
}

/// Read the daemon discovery file at `~/.coffer/daemon.json` and return the
/// port if present. Returns `None` on any I/O / parse failure — callers
/// treat that as "no daemon running."
///
/// We deliberately do not pull in serde_json here: the file is small and
/// the format is fixed (the daemon writes it), so a tiny string scan keeps
/// the desktop crate dependency-light.
pub fn read_daemon_port() -> Option<u16> {
    let home = env::var("HOME").ok().or_else(|| env::var("USERPROFILE").ok())?;
    let path = PathBuf::from(home).join(".coffer").join("daemon.json");
    let raw = fs::read_to_string(&path).ok()?;
    parse_daemon_port(&raw)
}

/// Extract the `"port"` value from the daemon discovery JSON via a tiny
/// hand-rolled scan — we avoid pulling `serde_json` into the desktop crate
/// (the file is small and the daemon controls its format). Returns `None`
/// for a missing key, a malformed value, or a port outside the u16 range.
fn parse_daemon_port(raw: &str) -> Option<u16> {
    let port_key = "\"port\"";
    let idx = raw.find(port_key)?;
    let after = &raw[idx + port_key.len()..];
    let colon = after.find(':')?;
    let tail = &after[colon + 1..];
    let mut digits = String::new();
    for ch in tail.chars() {
        if ch.is_ascii_digit() {
            digits.push(ch);
        } else if !digits.is_empty() {
            break;
        } else if !ch.is_whitespace() {
            // First non-digit, non-whitespace char before any digits — malformed.
            return None;
        }
    }
    digits.parse::<u16>().ok()
}

/// Extract the `"token"` string value from the daemon discovery JSON via the
/// same dependency-light scan as `parse_daemon_port`. The token is a
/// URL-safe base64 string (`[A-Za-z0-9_-]`, no embedded quotes/escapes), so a
/// plain "first quote after the colon → next quote" read is sufficient.
fn parse_daemon_token(raw: &str) -> Option<String> {
    let key = "\"token\"";
    let idx = raw.find(key)?;
    let after = &raw[idx + key.len()..];
    let colon = after.find(':')?;
    let open = after[colon + 1..].find('"')?;
    let rest = &after[colon + 1 + open + 1..];
    let close = rest.find('"')?;
    Some(rest[..close].to_string())
}

/// Read both the port and token from `~/.coffer/daemon.json`. Returns `None`
/// if the file is absent/unreadable or either field is missing.
pub fn read_daemon_info() -> Option<(u16, String)> {
    let home = env::var("HOME").ok().or_else(|| env::var("USERPROFILE").ok())?;
    let path = PathBuf::from(home).join(".coffer").join("daemon.json");
    let raw = fs::read_to_string(&path).ok()?;
    Some((parse_daemon_port(&raw)?, parse_daemon_token(&raw)?))
}

/// Best-effort check: is a daemon already listening on `127.0.0.1:<port>`?
pub fn daemon_is_listening(port: u16) -> bool {
    use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
    use std::time::Duration;
    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    TcpStream::connect_timeout(&addr.into(), Duration::from_millis(250)).is_ok()
}

/// Spawn the bundled `coffer-daemon` binary detached so it survives the app.
///
/// Behaviour:
///   1. Rate-limit: refuse if called within `RESTART_MIN_INTERVAL_SECS` of
///      the previous successful restart.
///   2. Detect-or-spawn: if `~/.coffer/daemon.json` lists a port and we can
///      open a TCP connection to it, return `started: false` with PID 0
///      instead of spawning a duplicate daemon.
///   3. Otherwise spawn the bundled binary detached and return its PID.
///
/// We deliberately use `std::process::Command` instead of the Tauri shell
/// sidecar API here so the spawned daemon survives the app's exit (the
/// shell plugin tears down child processes on app shutdown).
#[tauri::command]
pub fn restart_daemon(app: AppHandle) -> Result<RestartResult, String> {
    use std::time::{Duration, Instant};

    // Hold the rate-limit mutex across the ENTIRE operation (check +
    // detect-or-spawn + spawn + timestamp record). This intentionally
    // serializes concurrent `restart_daemon` calls so the second caller sees
    // either the just-recorded timestamp (→ rate-limited) or the now-running
    // daemon (→ detect-or-spawn no-op), closing the double-spawn race. The
    // blocking TCP probe (~250ms) + spawn happen under the lock; that's
    // acceptable for a rare, user-initiated manual restart. Early returns
    // (rate-limited Err, already-running Ok, spawn Err) simply drop the guard.
    let mut guard = LAST_RESTART_AT
        .lock()
        .map_err(|e| format!("restart lock poisoned: {e}"))?;

    // (1) Rate-limit guard. We only CHECK here against the last *successful*
    // spawn — we do NOT record `now` yet. The timestamp is recorded only
    // after we actually spawn a new daemon (see step 3), so an already-running
    // no-op or a spawn failure does not consume the rate-limit window and the
    // user can immediately retry to recover.
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

    // (2) Detect-or-spawn: if the discovery file lists a port and a daemon
    // is responsive on it, skip spawning a duplicate.
    if let Some(port) = read_daemon_port() {
        if daemon_is_listening(port) {
            log::info!("daemon already running on port {} — skipping spawn", port);
            return Ok(RestartResult { pid: 0, started: false });
        }
    }

    // (3) Spawn detached.
    let pid = spawn_daemon_detached(&app)?;

    // Record the rate-limit timestamp ONLY now — after a successful spawn —
    // so the window is never consumed by a no-op or a failed spawn. We still
    // hold the guard acquired at the top of the function.
    *guard = Some(Instant::now());

    log::info!("daemon restarted (pid {})", pid);
    Ok(RestartResult { pid, started: true })
}

/// Spawn the bundled `coffer-daemon` detached from the app (so it survives
/// app exit) and return its PID. Shared by `restart_daemon` and
/// `get_daemon_info`; the caller owns detect-or-spawn / rate-limit policy.
fn spawn_daemon_detached(app: &AppHandle) -> Result<u32, String> {
    use std::process::{Command, Stdio};

    let binary = bundled_daemon_path(app)?;
    let mut cmd = Command::new(&binary);
    cmd.stdout(Stdio::null())
        .stderr(Stdio::null())
        .stdin(Stdio::null());

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        unsafe {
            cmd.pre_exec(|| {
                // setsid detaches from the controlling terminal + process group.
                if libc::setsid() == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x00000008;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(DETACHED_PROCESS | CREATE_NO_WINDOW);
    }

    let child = cmd
        .spawn()
        .map_err(|e| format!("failed to spawn {}: {e}", binary.display()))?;
    let pid = child.id();
    // Don't `wait` on the handle — the daemon now lives independently.
    // `std::mem::forget` releases the Child struct without joining or killing
    // the OS process (stdio is already redirected to null + detached above).
    std::mem::forget(child);
    Ok(pid)
}

/// Daemon connection info handed to the web UI inside the desktop app.
#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DaemonInfo {
    /// `http://127.0.0.1:<port>/api/v1`
    pub base_url: String,
    pub token: String,
}

/// Return the running daemon's base URL + token for the webview to authenticate
/// with. The desktop app loads the frontend as bundled static assets, so the
/// frontend can't read `~/.coffer/daemon.json` itself — it calls this on
/// startup and sets `window.__COFFER_TOKEN__` / `__COFFER_BASE_URL__` before
/// any API request. Detect-or-spawn: reuse a live daemon, else spawn the
/// bundled one and wait (up to ~15s) for it to publish daemon.json + listen.
#[tauri::command]
pub fn get_daemon_info(app: AppHandle) -> Result<DaemonInfo, String> {
    use std::thread::sleep;
    use std::time::{Duration, Instant};

    let ready = |port: u16, token: String| DaemonInfo {
        base_url: format!("http://127.0.0.1:{port}/api/v1"),
        token,
    };

    // Fast path: a daemon is already running and reachable.
    if let Some((port, token)) = read_daemon_info() {
        if daemon_is_listening(port) {
            return Ok(ready(port, token));
        }
    }

    // Cold start: spawn the bundled daemon, then poll until it's listening.
    spawn_daemon_detached(&app)?;
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if let Some((port, token)) = read_daemon_info() {
            if daemon_is_listening(port) {
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
    fn parse_daemon_port_reads_well_formed_value() {
        assert_eq!(parse_daemon_port(r#"{"port": 8000, "pid": 1}"#), Some(8000));
    }

    #[test]
    fn parse_daemon_port_tolerates_spacing() {
        assert_eq!(parse_daemon_port(r#"{"port":8042}"#), Some(8042));
        assert_eq!(parse_daemon_port("{ \"port\" :   65535 }"), Some(65535));
    }

    #[test]
    fn parse_daemon_port_missing_key_is_none() {
        assert_eq!(parse_daemon_port(r#"{"pid": 1}"#), None);
    }

    #[test]
    fn parse_daemon_port_out_of_range_is_none() {
        // 70000 > u16::MAX — parse::<u16> fails, so we report "no port".
        assert_eq!(parse_daemon_port(r#"{"port": 70000}"#), None);
    }

    #[test]
    fn parse_daemon_port_non_numeric_value_is_none() {
        assert_eq!(parse_daemon_port(r#"{"port": "abc"}"#), None);
    }

    #[test]
    fn parse_daemon_token_reads_urlsafe_value() {
        // Obviously-fake fixture (URL-safe `-`/`_` chars, low entropy) so the
        // secrets scanner doesn't flag it as a real token.
        let raw = r#"{"port": 8000, "token": "EXAMPLE-url_safe-token_value", "pid": 1}"#;
        assert_eq!(parse_daemon_token(raw).as_deref(), Some("EXAMPLE-url_safe-token_value"));
    }

    #[test]
    fn parse_daemon_token_missing_key_is_none() {
        assert_eq!(parse_daemon_token(r#"{"port": 8000}"#), None);
    }

    #[test]
    fn parse_daemon_token_tolerates_spacing() {
        assert_eq!(parse_daemon_token(r#"{ "token" :   "abc123" }"#).as_deref(), Some("abc123"));
    }

    #[test]
    fn rate_limited_within_interval() {
        let prev = Instant::now();
        let now = prev + Duration::from_secs(2);
        assert!(restart_is_rate_limited(Some(prev), now, Duration::from_secs(5)));
    }

    #[test]
    fn not_rate_limited_after_interval() {
        let prev = Instant::now();
        let now = prev + Duration::from_secs(6);
        assert!(!restart_is_rate_limited(Some(prev), now, Duration::from_secs(5)));
    }

    #[test]
    fn not_rate_limited_on_first_call() {
        assert!(!restart_is_rate_limited(None, Instant::now(), Duration::from_secs(5)));
    }
}
