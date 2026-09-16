//! Starting a `coffer-daemon` detached from the app, so it survives app exit.
//!
//! Split out of `daemon.rs` to keep every file under the project's 400-line
//! cap (see `.agents/stack.md`).

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
    spawn_from_source(daemon_source(app)?)
}

/// The spawn decision, split from the `AppHandle`-bound resolution above so
/// the refusal to start a second daemon is unit-testable. A `Running` source
/// reaching here is the double-spawn the resolution chain exists to prevent
/// (FR-006), so it is an error naming the port rather than a spawn.
fn spawn_from_source(source: DaemonSource) -> Result<u32, String> {
    match source {
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
    // Append the daemon's stdout/stderr to ~/.coffer/logs/daemon.log so a
    // crash or stack trace from a GUI-spawned daemon is recoverable.
    spawn_detached(binary, open_daemon_log())
}

/// The detachment itself, with the log handle passed in rather than opened
/// here. Splitting it that way is what lets a test exercise the detachment —
/// the part that decides whether the daemon outlives the app — without
/// writing into the real `~/.coffer/logs/daemon.log`.
fn spawn_detached(binary: &Path, log: Option<std::fs::File>) -> Result<u32, String> {
    use std::process::{Command, Stdio};

    let mut cmd = Command::new(binary);
    cmd.stdin(Stdio::null());

    // Fall back to /dev/null when there is no log file. One handle per stream
    // (try_clone) so neither closes the other.
    match log {
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
        let err = spawn_detached(Path::new("/nonexistent/coffer-daemon"), None).unwrap_err();
        assert!(err.contains("/nonexistent/coffer-daemon"), "{err}");
    }

    /// FR-006's ordering, seen from the spawn side: the chain answering
    /// "a daemon is already up" must never be turned into a spawn.
    // acceptance(spec = "desktop-app", scenario = "the shell takes over a running daemon instead of spawning a second")
    #[test]
    fn a_running_source_is_refused_rather_than_spawned_beside() {
        let err = spawn_from_source(DaemonSource::Running {
            port: 8000,
            token: "tok".to_string(),
        })
        .unwrap_err();
        assert!(err.contains("8000"), "{err}");
        assert!(err.contains("already listening"), "{err}");
    }

    /// FR-009: a daemon the shell spawns must outlive the app, which is why
    /// it goes through `std::process::Command` + `setsid` rather than Tauri's
    /// managed-sidecar API (that one tears its children down on app exit).
    ///
    /// The observable consequence of `setsid` is that the child leads its own
    /// session and process group: it is no longer in the app's, so the signals
    /// that take the app down on quit — a group-wide SIGTERM, a SIGHUP on the
    /// controlling terminal — do not reach it. Asserting the group boundary is
    /// as close as a unit test gets to "the user quit and it kept serving"
    /// without a window to quit.
    // acceptance(spec = "desktop-app", scenario = "a spawned daemon outlives the app")
    #[cfg(unix)]
    #[test]
    fn a_spawned_daemon_leaves_the_apps_process_group() {
        use std::io::Write;
        use std::os::unix::fs::PermissionsExt;

        // A stand-in for the daemon: something that stays up long enough to
        // be inspected, and exits on its own if this test dies before the
        // cleanup below.
        let dir = std::env::temp_dir().join(format!("coffer-spawn-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("temp dir");
        let script = dir.join("fake-daemon");
        {
            let mut f = std::fs::File::create(&script).expect("create script");
            f.write_all(b"#!/bin/sh
exec sleep 30
").expect("write");
            f.set_permissions(std::fs::Permissions::from_mode(0o755))
                .expect("chmod");
        }

        let pid = spawn_detached(&script, None).expect("spawn");
        let cpid = pid as libc::pid_t;

        // SAFETY: plain reads of the child's process state; no mutation.
        let (child_group, our_group, alive) = unsafe {
            (
                libc::getpgid(cpid),
                libc::getpgid(0),
                libc::kill(cpid, 0) == 0,
            )
        };

        // Clean up before asserting, so a failure doesn't leak a sleeper.
        unsafe {
            libc::kill(cpid, libc::SIGKILL);
        }
        let _ = std::fs::remove_dir_all(&dir);

        assert!(alive, "the spawned daemon should still be running");
        assert!(child_group > 0, "getpgid failed for the child");
        assert_ne!(
            child_group, our_group,
            "setsid should have moved the daemon out of the app's process group, \
             so signals that end the app do not end it"
        );
        // setsid makes the child a session leader, i.e. its own group leader.
        assert_eq!(child_group, cpid, "the daemon should lead its own session");
    }
}
