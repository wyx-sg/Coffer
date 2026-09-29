//! What the menu bar item says and looks like, decided from what the shell
//! knows — the pure half of `tray.rs` (spec desktop-app "Show the daemon and
//! what needs the user in the menu bar").
//!
//! The menu is the native macOS menu: Coffer controls the icon, the labels and
//! their order, which items are enabled, the checkmark, and nothing else
//! (design canvas 1.5 Menu bar). Every one of those is a function of the state
//! below, so every one is decided here, where a test can read it, and
//! `tray.rs` only writes the answers onto the menu.

use crate::sync_presentation::tray_label;
use crate::tray_locale::{tray_text, Lang};
use crate::update_state::{Phase, UpdateStatus};

/// Whether the daemon is serving, as the last status poll found it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Daemon {
    /// No poll has answered yet — the few seconds of a launch.
    Connecting,
    Running {
        port: u16,
        version: String,
    },
    Offline,
}

/// The attention list's count, and the kind of its only item when it has one.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Attention {
    pub count: usize,
    pub only_kind: Option<String>,
}

/// The daemon's login service, as `GET /api/v1/daemon/residency` reports it.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Login {
    pub installed: bool,
    pub supported: bool,
}

/// Everything the menu bar item is drawn from.
#[derive(Clone, Debug)]
pub struct TrayState {
    pub daemon: Daemon,
    pub attention: Attention,
    /// The sync status a raised sync alert names (`sync_watch.rs`), if any.
    pub sync_alert: Option<String>,
    pub login: Option<Login>,
    pub update: UpdateStatus,
}

impl TrayState {
    pub fn new(update: UpdateStatus) -> TrayState {
        TrayState {
            daemon: Daemon::Connecting,
            attention: Attention::default(),
            sync_alert: None,
            login: None,
            update,
        }
    }

    fn online(&self) -> bool {
        matches!(self.daemon, Daemon::Running { .. })
    }
}

/// Which template image the menu bar shows.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Icon {
    Normal,
    /// A solid dot: something on Overview needs the user.
    Attention,
    /// Dimmed and struck through: no daemon is serving.
    Offline,
}

pub fn icon(state: &TrayState) -> Icon {
    match state.daemon {
        Daemon::Offline => Icon::Offline,
        _ if needs_you(state) > 0 => Icon::Attention,
        _ => Icon::Normal,
    }
}

/// How many things need the user. A raised sync alert counts even before the
/// attention list has been read, so the dot never lags the notification.
fn needs_you(state: &TrayState) -> usize {
    if !state.online() {
        return 0;
    }
    let listed = state.attention.count;
    if state.sync_alert.is_some() && listed == 0 {
        1
    } else {
        listed
    }
}

/// The first line: what the daemon is doing. Always disabled — it is a status,
/// not an action.
pub fn status_line(state: &TrayState, lang: Lang) -> String {
    let t = tray_text(lang);
    match &state.daemon {
        Daemon::Connecting => t.status_connecting.to_owned(),
        Daemon::Offline => t.status_offline.to_owned(),
        Daemon::Running { port, version } => t
            .status_running
            .replace("{port}", &port.to_string())
            .replace("{version}", version),
    }
}

/// The "N things need you" entry, or `None` when nothing does (the entry is
/// then out of the menu). A single sync problem is named rather than counted,
/// because its name is the whole message.
pub fn attention_label(state: &TrayState, lang: Lang) -> Option<String> {
    let n = needs_you(state);
    if n == 0 {
        return None;
    }
    let only_sync =
        state.attention.only_kind.as_deref() == Some("sync") || state.attention.count == 0;
    if n == 1 && only_sync {
        if let Some(status) = state.sync_alert.as_deref() {
            return Some(tray_label(status, lang));
        }
    }
    let t = tray_text(lang);
    Some(if n == 1 {
        t.needs_you_one.to_owned()
    } else {
        t.needs_you_many.replace("{n}", &n.to_string())
    })
}

/// The update entry's label and whether it can be chosen.
pub fn update_item(update: &UpdateStatus, lang: Lang) -> (String, bool) {
    let t = tray_text(lang);
    match update.phase {
        Phase::Checking => (t.checking_updates.to_owned(), false),
        Phase::Downloading => {
            let pct = match (update.downloaded, update.total) {
                (Some(done), Some(total)) if total > 0 => format!("{}%", done * 100 / total),
                _ => String::new(),
            };
            let label = t.downloading_update.replace("{pct}", &pct);
            (label.trim_end().to_owned(), false)
        }
        Phase::Installing => (t.installing_update.to_owned(), false),
        _ => match &update.available {
            Some(available) => (
                t.update_ready.replace("{version}", &available.version),
                true,
            ),
            None => (t.check_updates.to_owned(), true),
        },
    }
}

/// Restart when a daemon is serving, Start when none is. While the first poll
/// is outstanding it says Restart, which is what the handshake is about to
/// make true.
pub fn daemon_action(state: &TrayState, lang: Lang) -> &'static str {
    let t = tray_text(lang);
    match state.daemon {
        Daemon::Offline => t.start_daemon,
        _ => t.restart,
    }
}

/// The items that need a daemon — New conversation, Settings and Start at
/// login — are greyed out while none is serving.
pub fn needs_daemon_enabled(state: &TrayState) -> bool {
    state.online()
}

/// Start at login as `(enabled, checked)`: enabled only while a daemon answers
/// and the platform can install a login service; checked when it is installed.
pub fn login_item(state: &TrayState) -> (bool, bool) {
    match state.login {
        Some(login) if state.online() => (login.supported, login.installed),
        Some(login) => (false, login.installed),
        None => (false, false),
    }
}

pub fn tooltip(state: &TrayState, lang: Lang) -> &'static str {
    let t = tray_text(lang);
    match icon(state) {
        Icon::Offline => t.tooltip_offline,
        Icon::Attention => t.tooltip_attention,
        Icon::Normal => t.tooltip,
    }
}

#[cfg(test)]
#[path = "tray_state_tests.rs"]
mod tests;
