//! After an update relaunches the app, replace the daemon the previous version
//! left running (spec desktop-app "Check for updates against a signed release
//! manifest").
//!
//! The daemon is detached and outlives the app (spec desktop-app "Detach a
//! spawned daemon from the app"), so the relaunched shell finds the old
//! version's daemon still serving and would attach to it — the version-skew
//! check would then ask the user to restart it by hand, right after they asked
//! for the update. Instead the shell that installed the update marks the
//! process it relaunches (`updater::RELAUNCHED_FOR_UPDATE`, inherited through
//! `tauri::process::restart`), and that process's first handshake replaces a
//! skewed daemon through the one restart (`daemon::restart_daemon`) — the same
//! stop-then-spawn the tray and the offline banner use. Without the mark the
//! shell attaches and reports skew, as it always has.

use std::sync::atomic::{AtomicBool, Ordering};

use crate::daemon::{version_is_compatible, APP_VERSION};
use crate::updater::RELAUNCHED_FOR_UPDATE;

/// Whether this process was relaunched by an update and has not yet replaced
/// the previous daemon.
static PENDING: AtomicBool = AtomicBool::new(false);

/// Read the mark once, at startup, and take it off the environment so the
/// daemon this process spawns does not inherit it.
pub fn note_at_startup() {
    if let Some(from) = std::env::var_os(RELAUNCHED_FOR_UPDATE) {
        std::env::remove_var(RELAUNCHED_FOR_UPDATE);
        log::info!(
            "relaunched after updating from {} to {APP_VERSION}",
            from.to_string_lossy()
        );
        PENDING.store(true, Ordering::SeqCst);
    }
}

/// Consume the mark: `true` exactly once, and only in a relaunched process.
pub fn take() -> bool {
    PENDING.swap(false, Ordering::SeqCst)
}

/// Whether a daemon reporting `daemon_version` should be replaced now.
pub fn should_replace(relaunched: bool, daemon_version: &str) -> bool {
    relaunched && !version_is_compatible(APP_VERSION, daemon_version)
}

#[cfg(test)]
mod tests {
    use super::*;

    // acceptance(spec = "desktop-app", scenario = "installing an update relaunches onto the new version")
    #[test]
    fn a_relaunch_replaces_the_previous_versions_daemon() {
        assert!(should_replace(true, "0.0.1-previous"));
        assert!(should_replace(true, ""));
    }

    #[test]
    fn a_relaunch_keeps_a_daemon_that_already_matches() {
        assert!(!should_replace(true, APP_VERSION));
    }

    #[test]
    fn an_ordinary_launch_never_replaces_a_daemon() {
        // Skew on an ordinary launch is reported, not acted on (spec
        // desktop-app "Find or start a daemon by a fixed resolution order").
        assert!(!should_replace(false, "0.0.1-previous"));
    }

    #[test]
    fn the_mark_is_taken_once() {
        PENDING.store(true, Ordering::SeqCst);
        assert!(take());
        assert!(!take());
    }
}
