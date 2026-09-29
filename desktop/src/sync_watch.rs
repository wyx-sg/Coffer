//! The slow poll behind spec vault-sync "Say a vault needs a human where the
//! user already is", and the surfaces it drives.
//!
//! `sync_alert.rs` decides *whether* the vault's last round needs a human and
//! whether the user has already been told; this module asks the daemon, and
//! turns the answer into the three things a browser tab cannot do for itself —
//! a marked tray icon, a badged Dock icon, and one native notification.
//!
//! The poll is deliberately slow. A converge round runs on an interval measured
//! in tens of minutes, and a hold, a conflict or a failed push persists until a
//! person acts, so there is nothing a tighter loop could learn sooner. It also
//! never runs before the daemon is up: every tick first reads `daemon.json` and
//! asks the daemon's own unauthenticated status — the probe `resolve.rs` gates
//! its take-over on — and a tick that cannot reach a daemon leaves every surface
//! exactly as it found it rather than clearing a real alert because the daemon
//! happened to be restarting.
//!
//! That status also carries the `vault_sync` experimental feature, which
//! switches live. The tick that reads it is therefore short, and only the sync
//! poll behind it keeps the slow interval: while the feature is off the Sync
//! entry is out of the tray and nothing is polled or marked; the first tick
//! after it comes on puts the entry back and polls at once (`sync_gate.rs`).

use std::time::{Duration, Instant};

use tauri::image::Image;
use tauri::menu::{Menu, MenuItem};
use tauri::{AppHandle, Manager, Wry};
use tauri_plugin_notification::NotificationExt;

use crate::daemon_http::fetch_ok as fetch_json;
use crate::discovery::read_daemon_info;
use crate::sync_alert::{next_action, parse_sync_status, AlertAction};
use crate::sync_gate::{parse_vault_sync, plan_tick, MenuChange};
use crate::sync_presentation::{badge_rgba, notification_body, notification_title};
use crate::tray::{base_tray_icon, set_sync_attention, TrayMenu, SYNC_MENU_POSITION, TRAY_ID};
use crate::tray_locale;

/// The tray entry this module owns: a permanent route to the `/sync` page whose
/// label becomes the alert when a round needs a human. It is the click target
/// that requirement asks for — a desktop notification raised through this plugin exposes
/// no click handler on macOS, so the thing the user reaches for after reading
/// the notification is the tray, not the banner.
pub const SYNC_MENU_ITEM_ID: &str = "sync_status";

/// A short pause before the first tick, so it does not race the launch
/// handshake's detect-or-spawn. A tick that finds no daemon simply tries again.
const FIRST_TICK_DELAY: Duration = Duration::from_secs(5);
/// How often the daemon's status — and so the `vault_sync` flag — is read. The
/// feature switches without a restart, and this is how long the tray may lag it.
const FEATURE_TICK: Duration = Duration::from_secs(15);
/// How often the sync status is polled while the feature is on. Ten minutes. The alert's condition changes at most once a converge interval and
/// then waits for a person; polling harder buys nothing and costs a wakeup.
const POLL_INTERVAL: Duration = Duration::from_secs(600);

/// The Dock badge's text. A single character, because macOS draws it in a
/// circle the size of a favicon.
const DOCK_BADGE: &str = "!";

/// Start watching. Runs forever on its own thread; every effect it performs is
/// dispatched to the main thread by Tauri's own menu/tray/window wrappers.
pub fn start(app: AppHandle, tray: TrayMenu) {
    std::thread::spawn(move || {
        let TrayMenu { menu, sync: item } = tray;
        // The status the last raised notification was about. `None` means no
        // mark is showing — see `sync_alert::next_action` for the whole rule.
        let mut notified: Option<String> = None;
        // Whether the Sync entry is in the menu; `tray.rs` builds it out.
        let mut item_shown = false;
        // When the sync status was last asked, since the feature last came on.
        let mut last_sync_poll: Option<Instant> = None;
        std::thread::sleep(FIRST_TICK_DELAY);
        loop {
            if let Some((port, token, vault_sync)) = read_feature() {
                let plan = plan_tick(
                    vault_sync,
                    item_shown,
                    notified.is_some(),
                    last_sync_poll.map(|at| at.elapsed()),
                    POLL_INTERVAL,
                );
                if plan.clear_marks {
                    notified = None;
                    apply(&app, &AlertAction::Clear);
                }
                if !vault_sync {
                    last_sync_poll = None;
                }
                match plan.menu {
                    MenuChange::Show => item_shown = show_item(&menu, &item, true),
                    MenuChange::Hide => item_shown = show_item(&menu, &item, false),
                    MenuChange::Keep => {}
                }
                if plan.poll_sync {
                    last_sync_poll = Some(Instant::now());
                    let snapshot = fetch_json(port, &token, "/api/v1/sync/status")
                        .and_then(|body| parse_sync_status(&body));
                    if let Some(snapshot) = snapshot {
                        let action = next_action(notified.as_deref(), &snapshot);
                        match &action {
                            AlertAction::Raise(status) => notified = Some(status.clone()),
                            AlertAction::Clear => notified = None,
                            AlertAction::Nothing => {}
                        }
                        apply(&app, &action);
                    }
                }
            }
            std::thread::sleep(FEATURE_TICK);
        }
    });
}

/// Put the Sync entry into the menu, or take it out. Returns whether it is in
/// the menu afterwards; a failed change is logged and leaves the old answer, so
/// the next tick tries again.
fn show_item(menu: &Menu<Wry>, item: &MenuItem<Wry>, show: bool) -> bool {
    let result = if show {
        menu.insert(item, SYNC_MENU_POSITION)
    } else {
        menu.remove(item)
    };
    match result {
        Ok(()) => {
            log::info!(
                "sync.feature vault_sync={} tray sync item {}",
                if show { "on" } else { "off" },
                if show { "shown" } else { "removed" }
            );
            show
        }
        Err(e) => {
            log::warn!("sync.feature tray sync item change failed: {e}");
            !show
        }
    }
}

/// Bring the window up on the sync page. Wired to the tray entry.
pub fn open_sync_page(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let _ = window.show();
    let _ = window.set_focus();
    let _ = window.unminimize();
    let _ = window.eval(NAVIGATE_TO_SYNC_JS);
}

/// The frontend is one `createBrowserRouter` over `frontend/dist` (spec
/// desktop-app "Consume the one frontend build the daemon serves"), so the shell navigates it the
/// way the browser host's back button does — push the entry, then let the router's own `popstate`
/// listener read it — rather than gaining a second code path in the page. The
/// existing history state is carried over because React Router keys its listener
/// on the `idx` it keeps there; dropping it would make the event a no-op.
const NAVIGATE_TO_SYNC_JS: &str = "(function(){var s=window.history.state||{idx:0};\
     window.history.pushState(s,'','/sync');\
     window.dispatchEvent(new PopStateEvent('popstate',{state:s}));})()";

/// One tick's first question: is a daemon up, and is `vault_sync` on. `None`
/// for "could not ask", which is never an answer about the feature or the vault.
fn read_feature() -> Option<(u16, String, bool)> {
    let (port, token) = read_daemon_info()?;
    let body = fetch_json(port, &token, "/api/v1/daemon/status")?;
    let vault_sync = parse_vault_sync(&body)?;
    Some((port, token, vault_sync))
}

/// Perform one decision. Every failure here is logged and swallowed: a tray
/// that could not be repainted must not take the poll thread down with it.
fn apply(app: &AppHandle, action: &AlertAction) {
    match action {
        AlertAction::Raise(status) => {
            log::warn!("sync.attention raised status={status}");
            mark_icon(app, true);
            // Names the condition on the Sync entry and the tooltip, in the
            // interface language (`tray.rs`), and keeps it for a relabel.
            set_sync_attention(app, Some(status));
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
            mark_icon(app, false);
            set_sync_attention(app, None);
            set_dock_badge(app, None);
        }
        AlertAction::Nothing => {}
    }
}

/// Paint (or un-paint) the alert dot on the tray icon.
fn mark_icon(app: &AppHandle, marked: bool) {
    let Some(tray) = app.tray_by_id(TRAY_ID) else {
        return;
    };
    let base = base_tray_icon(app);
    let (width, height) = (base.width(), base.height());
    let icon = if marked {
        Image::new_owned(badge_rgba(base.rgba(), width, height), width, height)
    } else {
        base
    };
    if let Err(e) = tray.set_icon(Some(icon)) {
        log::warn!("sync.attention tray icon: {e}");
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
    fn the_navigation_script_targets_the_sync_route() {
        // `frontend/src/router.tsx` mounts the page at `/sync`; the shell and
        // the router are one artifact, so this is the one place the path is
        // repeated and it is asserted rather than assumed.
        assert!(NAVIGATE_TO_SYNC_JS.contains("'/sync'"));
        // The router keys its popstate listener on `history.state.idx`, so the
        // existing state must be carried through the push.
        assert!(NAVIGATE_TO_SYNC_JS.contains("window.history.state"));
        assert!(NAVIGATE_TO_SYNC_JS.contains("PopStateEvent"));
    }

    #[test]
    fn the_poll_is_slower_than_the_launch_and_far_slower_than_the_condition() {
        // The alert's condition is at most hourly and then waits for a person.
        assert!(POLL_INTERVAL >= Duration::from_secs(300));
        assert!(FIRST_TICK_DELAY < POLL_INTERVAL);
    }

    #[test]
    fn the_feature_tick_follows_a_switch_far_faster_than_the_sync_poll() {
        // The feature switches live; the tray should follow within a minute,
        // while the sync poll behind it keeps its slow interval.
        assert!(FEATURE_TICK <= Duration::from_secs(60));
        assert!(FEATURE_TICK < POLL_INTERVAL);
    }
}
