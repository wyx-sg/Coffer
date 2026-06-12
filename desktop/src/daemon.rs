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
pub fn read_daemon_port() -> Option<u16> {
    let home = env::var("HOME").ok().or_else(|| env::var("USERPROFILE").ok())?;
    let path = PathBuf::from(home).join(".coffer").join("daemon.json");
    let raw = fs::read_to_string(&path).ok()?;
    parse_daemon_port(&raw)
}

/// Extract the `"port"` value from the daemon discovery JSON. Returns `None`
/// for malformed JSON, a missing key, a non-numeric value, or a port outside
/// the u16 range. (serde_json is already in the Tauri dependency graph; the
/// previous hand-rolled string scan silently coupled to the daemon's
/// serializer — CODE-L7.)
fn parse_daemon_port(raw: &str) -> Option<u16> {
    let v: serde_json::Value = serde_json::from_str(raw).ok()?;
    u16::try_from(v.get("port")?.as_u64()?).ok()
}

/// Extract the `"token"` string value from the daemon discovery JSON.
fn parse_daemon_token(raw: &str) -> Option<String> {
    let v: serde_json::Value = serde_json::from_str(raw).ok()?;
    Some(v.get("token")?.as_str()?.to_string())
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

/// Ask the running daemon to shut itself down via its token-gated
/// `POST /api/v1/daemon/shutdown` route (a raw HTTP/1.1 request over
/// `TcpStream` — not worth an HTTP-client dependency for one loopback call).
/// The daemon replies 204 and SIGTERMs itself.
fn request_daemon_shutdown(port: u16, token: &str) -> Result<(), String> {
    use std::io::{Read, Write};
    use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};
    use std::time::Duration;

    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let mut stream = TcpStream::connect_timeout(&addr.into(), Duration::from_millis(500))
        .map_err(|e| format!("shutdown connect: {e}"))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .and_then(|_| stream.set_read_timeout(Some(Duration::from_secs(2))))
        .map_err(|e| format!("shutdown socket timeout: {e}"))?;
    let req = format!(
        "POST /api/v1/daemon/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\
         X-Coffer-Token: {token}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(req.as_bytes())
        .map_err(|e| format!("shutdown write: {e}"))?;
    let mut buf = [0u8; 32];
    let n = stream.read(&mut buf).map_err(|e| format!("shutdown read: {e}"))?;
    let head = String::from_utf8_lossy(&buf[..n]);
    if head.starts_with("HTTP/1.1 204") || head.starts_with("HTTP/1.0 204") {
        Ok(())
    } else {
        Err(format!("shutdown rejected: {}", head.lines().next().unwrap_or("")))
    }
}

/// Poll until nothing is listening on `port` (the old daemon has exited),
/// up to `timeout`. Returns `true` when the port is free.
fn wait_for_port_free(port: u16, timeout: std::time::Duration) -> bool {
    use std::time::Instant;
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if !daemon_is_listening(port) {
            return true;
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    false
}

/// Restart the daemon: stop the running one (if any), spawn a fresh one.
///
/// Behaviour:
///   1. Rate-limit: refuse if called within `RESTART_MIN_INTERVAL_SECS` of
///      the previous successful restart.
///   2. True restart: if `~/.coffer/daemon.json` lists a responsive daemon,
///      POST its token-gated /daemon/shutdown route and wait for the port
///      to free.
///   3. Spawn the bundled binary detached and return its PID.
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

    // (2) True restart: when a daemon is responsive, ask it to shut down
    // (token-gated POST /daemon/shutdown) and wait for the port to free
    // before spawning the replacement. Previously this branch was a silent
    // no-op, so "Restart daemon" did nothing exactly when a user would
    // reach for it (a wedged-but-listening daemon).
    if let Some((port, token)) = read_daemon_info() {
        if daemon_is_listening(port) {
            request_daemon_shutdown(port, &token)?;
            if !wait_for_port_free(port, Duration::from_secs(8)) {
                return Err(format!(
                    "daemon on port {port} did not stop within 8s of the shutdown request"
                ));
            }
            log::info!("daemon on port {} stopped for restart", port);
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

/// Sentinel wrapped around `$PATH` in the login-shell probe output so the
/// value survives any chatter a user's shell profile prints to stdout.
#[cfg(unix)]
const PATH_PROBE_MARKER: &str = "__COFFER_PATH__";

/// Extract the marker-delimited `$PATH` value from login-shell probe output.
/// Returns `None` when the markers are missing/unpaired or the value is empty
/// — callers treat that as "probe failed" and fall back.
#[cfg(unix)]
fn extract_marked_path(output: &str) -> Option<String> {
    let start = output.find(PATH_PROBE_MARKER)? + PATH_PROBE_MARKER.len();
    let end = output[start..].find(PATH_PROBE_MARKER)? + start;
    let path = output[start..end].trim();
    if path.is_empty() {
        None
    } else {
        Some(path.to_string())
    }
}

/// Ask the user's login shell for its `$PATH` (`$SHELL -lc`, so Homebrew /
/// nvm / pyenv exports in `~/.zprofile` etc. apply). Polls `try_wait` up to
/// `timeout` and kills the child on expiry rather than blocking the caller
/// on a hung profile. Returns `None` on any failure — callers fall back.
#[cfg(unix)]
fn login_shell_path(timeout: std::time::Duration) -> Option<String> {
    use std::io::Read;
    use std::process::{Command, Stdio};
    use std::time::Instant;

    let shell = env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let probe = format!("printf '%s%s%s' '{m}' \"$PATH\" '{m}'", m = PATH_PROBE_MARKER);
    let mut child = Command::new(&shell)
        .args(["-lc", &probe])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;

    let deadline = Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => break,
            Ok(Some(_)) => return None,
            Ok(None) if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
            Ok(None) => std::thread::sleep(std::time::Duration::from_millis(50)),
            Err(_) => return None,
        }
    }

    let mut out = String::new();
    child.stdout.take()?.read_to_string(&mut out).ok()?;
    extract_marked_path(&out)
}

/// Merge PATH sources for the daemon spawn, preserving order and deduping:
/// login-shell entries first, then the current process's entries, then
/// well-known tool dirs (Homebrew, `/usr/local/bin`, `~/.local/bin`,
/// `~/.cargo/bin`) as a safety net for when the login-shell probe fails.
/// Pure so it's unit-testable; empty segments are skipped.
#[cfg(unix)]
fn merged_spawn_path(
    login_path: Option<&str>,
    current_path: Option<&str>,
    home: Option<&str>,
) -> String {
    fn push_unique(entries: &mut Vec<String>, dir: &str) {
        if !dir.is_empty() && !entries.iter().any(|e| e == dir) {
            entries.push(dir.to_string());
        }
    }

    let mut entries: Vec<String> = Vec::new();
    for source in [login_path, current_path].into_iter().flatten() {
        for dir in source.split(':') {
            push_unique(&mut entries, dir);
        }
    }
    for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
        push_unique(&mut entries, dir);
    }
    if let Some(home) = home {
        for sub in [".local/bin", ".cargo/bin"] {
            push_unique(&mut entries, &format!("{home}/{sub}"));
        }
    }
    entries.join(":")
}

/// The PATH the spawned daemon should run with. The login-shell probe is
/// cached for the app's lifetime (`OnceLock`) — it costs a shell startup, and
/// the login PATH doesn't change while the app runs.
#[cfg(unix)]
fn daemon_spawn_path() -> String {
    static LOGIN_PATH: std::sync::OnceLock<Option<String>> = std::sync::OnceLock::new();
    let login =
        LOGIN_PATH.get_or_init(|| login_shell_path(std::time::Duration::from_secs(3)));
    merged_spawn_path(
        login.as_deref(),
        env::var("PATH").ok().as_deref(),
        env::var("HOME").ok().as_deref(),
    )
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

    // A Finder/Dock-launched .app inherits the minimal GUI PATH
    // (/usr/bin:/bin:/usr/sbin:/sbin), so the daemon — and the npx/uvx MCP
    // upstreams it spawns from that environment — would fail ENOENT. Hand the
    // daemon the user's login-shell PATH merged with well-known tool dirs.
    #[cfg(unix)]
    cmd.env("PATH", daemon_spawn_path());

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

    /// request_daemon_shutdown sends a token-carrying POST to the shutdown
    /// route and treats a 204 as success. Driven against an in-test TCP
    /// listener standing in for the daemon.
    #[test]
    fn request_daemon_shutdown_posts_token_and_accepts_204() {
        use std::io::{Read, Write};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        let handle = std::thread::spawn(move || {
            let (mut sock, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let n = sock.read(&mut buf).expect("read");
            let req = String::from_utf8_lossy(&buf[..n]).into_owned();
            sock.write_all(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
                .expect("write");
            req
        });

        request_daemon_shutdown(port, "tok-123").expect("shutdown ok");
        let req = handle.join().expect("server thread");
        assert!(req.starts_with("POST /api/v1/daemon/shutdown HTTP/1.1\r\n"), "{req}");
        assert!(req.contains("X-Coffer-Token: tok-123\r\n"), "{req}");
    }

    #[test]
    fn request_daemon_shutdown_rejects_non_204() {
        use std::io::{Read, Write};
        use std::net::TcpListener;

        let listener = TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            let (mut sock, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = sock.read(&mut buf);
            let _ = sock.write_all(b"HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n");
        });

        let err = request_daemon_shutdown(port, "bad-token").unwrap_err();
        assert!(err.contains("401"), "{err}");
    }

    #[test]
    fn wait_for_port_free_returns_true_when_nothing_listens() {
        use std::net::TcpListener;
        // Grab a free port, then release it so nothing is listening.
        let port = {
            let l = TcpListener::bind("127.0.0.1:0").unwrap();
            l.local_addr().unwrap().port()
        };
        assert!(wait_for_port_free(port, Duration::from_millis(300)));
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

    // --- daemon-spawn PATH (P0-6): a Finder/Dock-launched .app inherits the
    // minimal GUI PATH, so the daemon (and its npx/uvx MCP upstreams) needs
    // the user's login-shell PATH merged back in before spawn. ---

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_puts_login_shell_entries_first() {
        let merged = merged_spawn_path(
            Some("/opt/homebrew/bin:/usr/bin"),
            Some("/usr/bin:/bin"),
            None,
        );
        assert_eq!(merged, "/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin");
    }

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_without_login_shell_appends_well_known_dirs() {
        let merged = merged_spawn_path(None, Some("/usr/bin:/bin"), Some("/Users/u"));
        assert_eq!(
            merged,
            "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin:/Users/u/.local/bin:/Users/u/.cargo/bin"
        );
    }

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_dedupes_keeping_first_occurrence() {
        let merged = merged_spawn_path(
            Some("/usr/local/bin:/usr/bin"),
            Some("/usr/bin:/usr/local/bin:/bin"),
            None,
        );
        assert_eq!(merged, "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin");
    }

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_skips_empty_segments() {
        let merged = merged_spawn_path(Some(":/usr/bin::"), None, None);
        assert_eq!(merged, "/usr/bin:/opt/homebrew/bin:/usr/local/bin");
    }

    #[cfg(unix)]
    #[test]
    fn extract_marked_path_ignores_profile_chatter() {
        let out = format!("welcome banner\n{m}/a:/b{m}\ntrailing", m = PATH_PROBE_MARKER);
        assert_eq!(extract_marked_path(&out).as_deref(), Some("/a:/b"));
    }

    #[cfg(unix)]
    #[test]
    fn extract_marked_path_missing_or_unpaired_markers_is_none() {
        assert_eq!(extract_marked_path("/usr/bin:/bin"), None);
        assert_eq!(extract_marked_path(&format!("{PATH_PROBE_MARKER}/usr/bin")), None);
    }

    #[cfg(unix)]
    #[test]
    fn extract_marked_path_empty_value_is_none() {
        assert_eq!(extract_marked_path(&format!("{m}  {m}", m = PATH_PROBE_MARKER)), None);
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
