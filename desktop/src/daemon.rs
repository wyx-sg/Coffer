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

use tauri::{AppHandle, Manager};

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

/// Locate the bundled `coffer-daemon` binary in the app's resource directory.
///
/// Probes (in order): macOS `Contents/MacOS/`, resource dir itself, and one
/// level up. See `shim::bundled_shim_path` for the platform-layout rationale.
pub fn bundled_daemon_path(app: &AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;

    let exe = if cfg!(target_os = "windows") {
        "coffer-daemon.exe"
    } else {
        "coffer-daemon"
    };

    let parent = resource_dir.parent().map(|p| p.to_owned());
    let macos_dir = parent.as_deref().map(|p| p.join("MacOS"));

    let candidates: Vec<PathBuf> = [
        macos_dir.as_deref().map(|p| p.join(exe)),
        Some(resource_dir.join(exe)),
        parent.as_deref().map(|p| p.join(exe)),
    ]
    .into_iter()
    .flatten()
    .collect();

    for c in &candidates {
        if c.is_file() {
            return Ok(c.clone());
        }
    }

    Err(format!(
        "coffer-daemon not found near {} (searched {} candidates)",
        resource_dir.display(),
        candidates.len()
    ))
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
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};

    // (1) Rate-limit guard. Hold the lock only long enough to read+update.
    {
        let mut guard = LAST_RESTART_AT
            .lock()
            .map_err(|e| format!("restart lock poisoned: {e}"))?;
        let now = Instant::now();
        if let Some(prev) = *guard {
            let elapsed = now.duration_since(prev);
            if elapsed < Duration::from_secs(RESTART_MIN_INTERVAL_SECS) {
                let remaining = RESTART_MIN_INTERVAL_SECS - elapsed.as_secs();
                return Err(format!(
                    "restart_daemon: rate-limited; retry in {}s",
                    remaining.max(1)
                ));
            }
        }
        *guard = Some(now);
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
    let binary = bundled_daemon_path(&app)?;

    let mut cmd = Command::new(&binary);
    cmd.stdout(Stdio::null())
        .stderr(Stdio::null())
        .stdin(Stdio::null());

    // Detach so the daemon outlives the app process.
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
    // `std::mem::forget` releases the Child struct without joining or
    // killing the OS process. The daemon's own SIGCHLD / lifecycle is
    // unaffected because we already redirected its stdio to null and
    // detached the controlling terminal above.
    std::mem::forget(child);

    log::info!("daemon restarted (pid {})", pid);
    Ok(RestartResult { pid, started: true })
}
