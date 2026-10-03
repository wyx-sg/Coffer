//! What the menu bar item says and looks like, decided from what the shell
//! knows — the pure half of `tray.rs` (spec desktop-app "Show the daemon and
//! what needs the user in the menu bar").
//!
//! The menu is the native macOS menu: Coffer controls the icon, the count beside
//! it, the labels and their order, and nothing else (design canvas 1.3.01
//! Normal, 1.3.02 Needs you, 1.3.03 Daemon offline). Every one of those is a function of the state
//! below, so every one is decided here, where a test can read it, and
//! `tray.rs` only writes the answers onto the menu.

use crate::tray_locale::{tray_text, Lang};

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

/// How many items the Overview's attention list holds (ignored ones are not in
/// it).
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Attention {
    pub count: usize,
}

/// Everything the menu bar item is drawn from.
#[derive(Clone, Debug)]
pub struct TrayState {
    pub daemon: Daemon,
    pub attention: Attention,
    /// Whether a sync alert is raised (`sync_watch.rs`); it counts as one
    /// thing until the attention list lists it.
    pub sync_alert: bool,
}

impl TrayState {
    pub fn new() -> TrayState {
        TrayState {
            daemon: Daemon::Connecting,
            attention: Attention::default(),
            sync_alert: false,
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
    /// Dimmed and struck through: no daemon is serving.
    Offline,
}

pub fn icon(state: &TrayState) -> Icon {
    match state.daemon {
        Daemon::Offline => Icon::Offline,
        _ => Icon::Normal,
    }
}

/// How many things need the user. A raised sync alert counts even before the
/// attention list has been read, so the count never lags the notification.
pub fn needs_you(state: &TrayState) -> usize {
    if !state.online() {
        return 0;
    }
    let listed = state.attention.count;
    if state.sync_alert && listed == 0 {
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
/// then out of the menu).
pub fn attention_label(state: &TrayState, lang: Lang) -> Option<String> {
    let t = tray_text(lang);
    match needs_you(state) {
        0 => None,
        1 => Some(t.needs_you_one.to_owned()),
        n => Some(t.needs_you_many.replace("{n}", &n.to_string())),
    }
}

/// The count drawn beside the icon: the number, "9+" past nine, nothing when
/// nothing needs the user or no daemon is serving.
pub fn title(state: &TrayState) -> Option<String> {
    match needs_you(state) {
        0 => None,
        n if n > 9 => Some("9+".to_owned()),
        n => Some(n.to_string()),
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

pub fn tooltip(state: &TrayState, lang: Lang) -> &'static str {
    let t = tray_text(lang);
    match icon(state) {
        Icon::Offline => t.tooltip_offline,
        Icon::Normal if needs_you(state) > 0 => t.tooltip_attention,
        Icon::Normal => t.tooltip,
    }
}

#[cfg(test)]
#[path = "tray_state_tests.rs"]
mod tests;
