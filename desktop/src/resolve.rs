//! Where the shell gets a daemon from — the five-step resolution chain.
//!
//! The order is fixed by the desktop-shell ADR
//! (`docs/decisions/desktop-shell-over-a-shared-frontend.md`):
//!
//!   1. an already-running daemon named by `~/.coffer/daemon.json` — taken
//!      over, never re-spawned
//!   2. inside the app bundle (`externalBin`, staged by `make desktop`)
//!   3. `~/.coffer/bin/coffer-daemon` (where the daemon's own frozen-start
//!      path, spec daemon "Deploy frozen sibling binaries and back up the
//!      vault before migrating", deploys it)
//!   4. `coffer-daemon` on `$PATH`
//!   5. otherwise: a message telling the user to install the Coffer CLI
//!
//! **The liveness probe has to be first**, and it is the one place the order
//! is not merely a preference. Steps 2-4 all answer the same question — which
//! binary would we spawn — while step 1 answers a different one: whether to
//! spawn at all. Ask them the other way round and a bundled build opens a
//! second daemon beside the one the user already started from the CLI. Under
//! the fixed-port default (spec daemon "Bind a fixed, settable port") that second daemon cannot
//! bind and refuses to start, so the symptom is an error on an app that should
//! simply have attached to what was already there.
//!
//! Steps 2-4 are written in their final form on purpose: the app can be built
//! with or without bundled binaries and only the packaging changes, never this
//! code.

use std::env;
use std::path::PathBuf;

use tauri::AppHandle;

use crate::discovery::{daemon_responds_ok, read_daemon_info};
use crate::env_path::{daemon_spawn_path, path_candidates};
use crate::sidecar::resolve_sidecar;

/// Where a daemon is going to come from.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DaemonSource {
    /// Steps 2, 3 and 4 — a binary to spawn. `origin` is for logging and
    /// error copy only.
    Binary { path: PathBuf, origin: &'static str },
    /// Step 1 — a daemon that is already up. Take it over; do not spawn.
    Running { port: u16, token: String },
}

/// Step 5. The whole first-run experience for someone who downloaded only the
/// app, so it names the fix rather than the failure.
pub const DAEMON_NOT_FOUND: &str = "\
Coffer can't find its daemon (coffer-daemon), so there is nothing to connect to.

Looked in:
  1. a running daemon recorded in ~/.coffer/daemon.json
  2. this app's own bundle
  3. ~/.coffer/bin/coffer-daemon
  4. coffer-daemon on your PATH

The daemon ships with the Coffer CLI. Install it, then reopen Coffer:

  curl -fsSL --proto '=https' --tlsv1.2 \\
    https://wyx-sg.github.io/Coffer/install.sh | sh

If you already installed the CLI, make sure ~/.coffer/bin is on your PATH.";

/// The chain itself, over lazily-evaluated probes so a hit at step 1 never
/// pays for the filesystem walk behind steps 2-4. Each probe is a closure
/// rather than a value precisely so the ORDER lives here and nowhere else —
/// the impure wrapper below supplies the real probes, tests supply stubs.
pub fn resolve_daemon_source<R, B, U, P>(
    running: R,
    bundled: B,
    user_bin: U,
    on_path: P,
) -> Result<DaemonSource, String>
where
    R: FnOnce() -> Option<(u16, String)>,
    B: FnOnce() -> Option<PathBuf>,
    U: FnOnce() -> Option<PathBuf>,
    P: FnOnce() -> Option<PathBuf>,
{
    if let Some((port, token)) = running() {
        return Ok(DaemonSource::Running { port, token });
    }
    if let Some(path) = bundled() {
        return Ok(DaemonSource::Binary {
            path,
            origin: "app bundle",
        });
    }
    if let Some(path) = user_bin() {
        return Ok(DaemonSource::Binary {
            path,
            origin: "~/.coffer/bin",
        });
    }
    if let Some(path) = on_path() {
        return Ok(DaemonSource::Binary {
            path,
            origin: "PATH",
        });
    }
    Err(DAEMON_NOT_FOUND.to_string())
}

/// The executable name of the daemon on this platform.
pub fn daemon_exe_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "coffer-daemon.exe"
    } else {
        "coffer-daemon"
    }
}

/// Step 3's path, given the user's home dir. Pure so the layout is testable.
/// Mirrors where the daemon's own frozen-start deploy puts it (spec daemon
/// "Deploy frozen sibling binaries and back up the vault before migrating").
pub fn user_bin_daemon_path(home: &str) -> PathBuf {
    PathBuf::from(home)
        .join(".coffer")
        .join("bin")
        .join(daemon_exe_name())
}

/// Run the chain against the real machine.
pub fn daemon_source(app: &AppHandle) -> Result<DaemonSource, String> {
    resolve_daemon_source(
        // (1) a live daemon — an HTTP status probe, not a bare TCP connect,
        // so a port-squatter on the recorded port can't pass for a daemon.
        // First, so the app attaches to whatever is already serving instead
        // of racing it for the port.
        || read_daemon_info().filter(|(port, _)| daemon_responds_ok(*port)),
        // (2) staged by `externalBin` into the .app.
        || resolve_sidecar(app, &["coffer-daemon"]).ok(),
        // (3) ~/.coffer/bin, where the daemon's own frozen-start deploy puts it.
        || {
            let home = env::var("HOME")
                .ok()
                .or_else(|| env::var("USERPROFILE").ok())?;
            let path = user_bin_daemon_path(&home);
            path.is_file().then_some(path)
        },
        // (4) $PATH — the same merged PATH a spawned daemon is handed, so
        // "on PATH" means one thing in this app.
        || {
            path_candidates(&daemon_spawn_path(), daemon_exe_name())
                .into_iter()
                .find(|c| c.is_file())
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn some(p: &str) -> Option<PathBuf> {
        Some(PathBuf::from(p))
    }

    fn resolved(
        running: Option<(u16, String)>,
        bundled: Option<PathBuf>,
        user_bin: Option<PathBuf>,
        on_path: Option<PathBuf>,
    ) -> Result<DaemonSource, String> {
        resolve_daemon_source(|| running, || bundled, || user_bin, || on_path)
    }

    /// The one ordering that is correctness rather than preference: a bundled
    /// build must attach to the daemon the user already started, not spawn a
    /// rival for its port.
    // acceptance(spec = "desktop-app", scenario = "the shell takes over a running daemon instead of spawning a second")
    #[test]
    fn a_running_daemon_wins_over_everything_else_including_the_bundle() {
        let got = resolved(
            Some((8000, "tok".into())),
            some("/A/Coffer.app/Contents/MacOS/coffer-daemon"),
            some("/h/.coffer/bin/coffer-daemon"),
            some("/usr/local/bin/coffer-daemon"),
        );
        assert_eq!(
            got,
            Ok(DaemonSource::Running {
                port: 8000,
                token: "tok".into()
            })
        );
    }

    #[test]
    fn the_bundle_is_the_first_binary_probe() {
        let got = resolved(
            None,
            some("/A/Coffer.app/Contents/MacOS/coffer-daemon"),
            some("/h/.coffer/bin/coffer-daemon"),
            some("/usr/local/bin/coffer-daemon"),
        );
        assert_eq!(
            got,
            Ok(DaemonSource::Binary {
                path: PathBuf::from("/A/Coffer.app/Contents/MacOS/coffer-daemon"),
                origin: "app bundle",
            })
        );
    }

    #[test]
    fn user_bin_beats_path() {
        let got = resolved(
            None,
            None,
            some("/h/.coffer/bin/coffer-daemon"),
            some("/usr/local/bin/coffer-daemon"),
        );
        assert_eq!(
            got,
            Ok(DaemonSource::Binary {
                path: PathBuf::from("/h/.coffer/bin/coffer-daemon"),
                origin: "~/.coffer/bin",
            })
        );
    }

    #[test]
    fn path_is_the_last_binary_probe() {
        let got = resolved(None, None, None, some("/usr/local/bin/coffer-daemon"));
        assert_eq!(
            got,
            Ok(DaemonSource::Binary {
                path: PathBuf::from("/usr/local/bin/coffer-daemon"),
                origin: "PATH",
            })
        );
    }

    #[test]
    fn nothing_found_tells_the_user_to_install_the_cli() {
        let err = resolved(None, None, None, None).unwrap_err();
        assert_eq!(err, DAEMON_NOT_FOUND);
        // The message is a stranger's entire first run — it must carry the
        // installer, not just the complaint.
        assert!(err.contains("install.sh"), "{err}");
        assert!(err.contains("~/.coffer/bin"), "{err}");
    }

    /// Later probes must not run once an earlier one hits — steps 2-4 walk the
    /// filesystem and the merged `$PATH`, which an already-attached app should
    /// never pay for. The user-visible half is that the three probes that
    /// answer "which binary would we spawn" never even run, so no spawn can
    /// follow from them.
    // acceptance(spec = "desktop-app", scenario = "the shell takes over a running daemon instead of spawning a second")
    #[test]
    fn later_probes_are_not_evaluated_once_a_step_hits() {
        use std::cell::Cell;
        let touched = Cell::new(false);
        let got = resolve_daemon_source(
            || Some((8000, "tok".to_string())),
            || {
                touched.set(true);
                None
            },
            || {
                touched.set(true);
                None
            },
            || {
                touched.set(true);
                None
            },
        );
        assert!(got.is_ok());
        assert!(!touched.get(), "probes after the first hit must not run");
    }

    #[test]
    fn user_bin_path_sits_under_dot_coffer_bin() {
        let p = user_bin_daemon_path("/Users/u");
        assert_eq!(p.parent().unwrap(), PathBuf::from("/Users/u/.coffer/bin"));
        assert_eq!(p.file_name().unwrap().to_string_lossy(), daemon_exe_name());
    }

    #[test]
    #[cfg(not(target_os = "windows"))]
    fn daemon_exe_name_has_no_extension_on_posix() {
        assert_eq!(daemon_exe_name(), "coffer-daemon");
    }

    #[test]
    #[cfg(target_os = "windows")]
    fn daemon_exe_name_has_exe_extension_on_windows() {
        assert_eq!(daemon_exe_name(), "coffer-daemon.exe");
    }
}
