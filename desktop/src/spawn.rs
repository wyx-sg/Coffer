//! Starting a `coffer-daemon` detached from the app, so it survives app exit.
//!
//! Split out of `daemon.rs` to keep every file under the project's 400-line
//! cap (see `agents/stack.md`).

use std::path::Path;

use tauri::AppHandle;

use crate::env_path::daemon_spawn_path;
use crate::logging::open_daemon_log;
use crate::resolve::{daemon_source, DaemonSource};

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
    fn spawning_a_missing_binary_names_the_path_it_tried() {
        let err = spawn_daemon_detached(Path::new("/nonexistent/coffer-daemon")).unwrap_err();
        assert!(err.contains("/nonexistent/coffer-daemon"), "{err}");
    }
}
