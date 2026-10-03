//! The slow poll behind spec vault-sync "Say a vault needs a human where the
//! user already is", and the surfaces it drives.
//!
//! `sync_alert.rs` decides *whether* the vault's last round needs a human and
//! whether the user has already been told; this module asks the daemon, and
//! turns the answer into the three things a browser tab cannot do for itself —
//! a marked menu bar icon, a badged Dock icon, and one native notification.
//!
//! It has no thread of its own: `tray_watch.rs` reads the daemon's status on
//! its short tick and calls this once per tick that reached a daemon. A tick
//! that could not reach a daemon never calls it, which leaves every surface
//! exactly as it was rather than clearing a real alert because the daemon
//! happened to be restarting.
//!
//! The sync poll behind it keeps a slow interval. A converge round runs on an
//! interval measured in tens of minutes, and a hold, a conflict or a failed
//! push persists until a person acts, so there is nothing a tighter loop could
//! learn sooner. The first tick polls at once.

use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};
use tauri_plugin_notification::NotificationExt;

use crate::daemon_http::fetch_ok as fetch_json;
use crate::sync_alert::{next_action, parse_sync_status, AlertAction};
use crate::sync_presentation::{notification_body, notification_title};
use crate::tray::set_sync_alert;
use crate::tray_locale;

/// How often the sync status is polled. Ten minutes.
/// The alert's condition changes at most once a converge interval and then
/// waits for a person; polling harder buys nothing and costs a wakeup.
pub const POLL_INTERVAL: Duration = Duration::from_secs(600);

/// The Dock badge's text. A single character, because macOS draws it in a
/// circle the size of a favicon.
const DOCK_BADGE: &str = "!";

/// What the watcher remembers between ticks.
#[derive(Default)]
pub struct SyncWatch {
    /// The status the last raised notification was about. `None` means no
    /// mark is showing — see `sync_alert::next_action` for the whole rule.
    notified: Option<String>,
    /// When the sync status was last asked; `None` before the first poll.
    last_sync_poll: Option<Instant>,
}

impl SyncWatch {
    /// One tick, given a daemon that answered.
    pub fn tick(&mut self, app: &AppHandle, port: u16, token: &str) {
        if !poll_due(self.last_sync_poll.map(|at| at.elapsed()), POLL_INTERVAL) {
            return;
        }
        self.last_sync_poll = Some(Instant::now());
        let snapshot = fetch_json(port, token, "/api/v1/sync/status")
            .and_then(|body| parse_sync_status(&body));
        if let Some(snapshot) = snapshot {
            let action = next_action(self.notified.as_deref(), &snapshot);
            match &action {
                AlertAction::Raise(status) => self.notified = Some(status.clone()),
                AlertAction::Clear => self.notified = None,
                AlertAction::Nothing => {}
            }
            apply(app, &action);
        }
    }
}

/// Whether this tick asks for the sync status: at once on the first tick, then
/// once a `sync_interval` has passed since the last poll.
fn poll_due(since_sync_poll: Option<Duration>, sync_interval: Duration) -> bool {
    since_sync_poll.is_none_or(|elapsed| elapsed >= sync_interval)
}

/// Perform one decision. Every failure here is logged and swallowed: a tray
/// that could not be repainted must not take the poll thread down with it.
fn apply(app: &AppHandle, action: &AlertAction) {
    match action {
        AlertAction::Raise(status) => {
            log::warn!("sync.attention raised status={status}");
            // The menu bar's count (`tray_state.rs`).
            set_sync_alert(app, true);
            set_dock_badge(app, Some(DOCK_BADGE));
            let lang = tray_locale::current();
            if let Err(e) = app
                .notification()
                .builder()
                .title(notification_title(lang))
                .body(notification_body(status, lang))
                .show()
            {
                log::warn!("sync.attention notification failed: {e}");
            }
        }
        AlertAction::Clear => {
            log::info!("sync.attention cleared");
            set_sync_alert(app, false);
            set_dock_badge(app, None);
        }
        AlertAction::Nothing => {}
    }
}

/// The Dock badge. macOS is the only platform the shell ships on (spec
/// desktop-app "Ship the desktop tier as a macOS arm64 dmg") and the only one where Tauri exposes
/// this at all, so the other builds — the Linux `cargo check` CI leg among them — get a no-op.
#[cfg(target_os = "macos")]
fn set_dock_badge(app: &AppHandle, label: Option<&str>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_badge_label(label.map(str::to_owned));
    }
}

#[cfg(not(target_os = "macos"))]
fn set_dock_badge(_app: &AppHandle, _label: Option<&str>) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_poll_is_far_slower_than_the_condition_needs() {
        // The alert's condition is at most hourly and then waits for a person.
        assert!(POLL_INTERVAL >= Duration::from_secs(300));
        assert!(crate::tray_watch::STATUS_TICK < POLL_INTERVAL);
    }

    #[test]
    fn the_first_tick_polls_at_once() {
        assert!(poll_due(None, POLL_INTERVAL));
    }

    #[test]
    fn the_sync_poll_keeps_its_own_slow_interval() {
        assert!(!poll_due(Some(Duration::from_secs(30)), POLL_INTERVAL));
        assert!(poll_due(Some(POLL_INTERVAL), POLL_INTERVAL));
    }
}
