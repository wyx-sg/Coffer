//! Starting a `coffer-daemon` detached from the app, so it survives app exit.
//!
//! Split out of `daemon.rs` to keep every file under the project's 400-line
//! cap (see `agents/stack.md`).

use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use tauri::AppHandle;

use crate::env_path::daemon_spawn_path;
use crate::resolve::{daemon_source, DaemonSource};

/// Path the daemon's stdout/stderr is appended to, given the user's home dir.
/// Pure so it's unit-testable. Mirrors the CLI spawn (backend `_client.py`),
/// which logs to this same file.
fn daemon_log_path(home: &str) -> PathBuf {
    PathBuf::from(home)
        .join(".coffer")
        .join("logs")
        .join("daemon.log")
}

/// Open `~/.coffer/logs/daemon.log` for appending, creating the logs directory
/// if needed. Returns `None` on any failure (no home, mkdir/open error) so the
/// caller falls back to `/dev/null` rather than failing the spawn.
fn open_daemon_log() -> Option<fs::File> {
    let home = env::var("HOME")
        .ok()
        .or_else(|| env::var("USERPROFILE").ok())?;
    let path = daemon_log_path(&home);
    fs::create_dir_all(path.parent()?).ok()?;
    fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .ok()
}

/// Resolve a daemon (the five-step chain in `resolve.rs`) and spawn it
/// detached, returning its PID.
///
/// Errors when the chain finds a daemon that is already *running* — the
/// callers that spawn have already stopped it, so reaching this branch means
/// something else took the port back, and spawning a second one would be
/// wrong. Callers that are happy to take a running daemon over call
/// [`crate::resolve::daemon_source`] themselves.
pub fn spawn_resolved_daemon(app: &AppHandle) -> Result<u32, String> {
    match daemon_source(app)? {
        DaemonSource::Binary { path, origin } => {
            log::info!("spawning coffer-daemon from {origin}: {}", path.display());
            spawn_daemon_detached(&path)
        }
        DaemonSource::Running { port, .. } => Err(format!(
            "a daemon is already listening on port {port}; stop it before spawning another"
        )),
    }
}

/// Spawn `binary` detached from the app (so it survives app exit) and return
/// its PID.
///
/// We deliberately use `std::process::Command` instead of the Tauri shell
/// sidecar API so the spawned daemon outlives the app (the shell plugin tears
/// down child processes on app shutdown).
fn spawn_daemon_detached(binary: &Path) -> Result<u32, String> {
    use std::process::{Command, Stdio};

    let mut cmd = Command::new(binary);
    cmd.stdin(Stdio::null());

    // Append the daemon's stdout/stderr to ~/.coffer/logs/daemon.log so a
    // crash or stack trace from a GUI-spawned daemon is recoverable. Fall back
    // to /dev/null only if the log file cannot be opened. One handle per
    // stream (try_clone) so neither closes the other.
    match open_daemon_log() {
        Some(log) => match log.try_clone() {
            Ok(log_err) => {
                cmd.stdout(Stdio::from(log)).stderr(Stdio::from(log_err));
            }
            Err(_) => {
                cmd.stdout(Stdio::from(log)).stderr(Stdio::null());
            }
        },
        None => {
            cmd.stdout(Stdio::null()).stderr(Stdio::null());
        }
    }

    // A Finder/Dock-launched .app inherits the minimal GUI PATH, so the daemon
    // — and the npx/uvx MCP upstreams it spawns from that environment — would
    // fail ENOENT. Hand it the user's login-shell PATH merged with well-known
    // tool dirs (see `env_path.rs`).
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
    // the OS process (stdio is already redirected + detached above).
    std::mem::forget(child);
    Ok(pid)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn daemon_log_path_is_under_coffer_logs() {
        // The daemon's stdout/stderr append here instead of /dev/null so a
        // GUI-spawned daemon's crash is recoverable. Mirrors the CLI spawn
        // (backend _client.py), which logs to the same file.
        assert_eq!(
            daemon_log_path("/Users/u"),
            PathBuf::from("/Users/u/.coffer/logs/daemon.log")
        );
    }

    #[test]
    fn spawning_a_missing_binary_names_the_path_it_tried() {
        let err = spawn_daemon_detached(Path::new("/nonexistent/coffer-daemon")).unwrap_err();
        assert!(err.contains("/nonexistent/coffer-daemon"), "{err}");
    }
}
