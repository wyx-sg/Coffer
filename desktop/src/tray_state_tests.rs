//! Tests for `tray_state.rs`: the menu bar as the design canvas draws it
//! (1.5.01 Normal, 1.5.02 Needs you, 1.5.03 Daemon offline, 1.5.04 Update
//! available).

use super::*;
use crate::update_state::{AvailableUpdate, UpdateStatus};

fn running() -> TrayState {
    let mut s = TrayState::new(UpdateStatus::new("0.4.2", true));
    s.daemon = Daemon::Running {
        port: 8000,
        version: "0.4.2".into(),
    };
    s.login = Some(Login {
        installed: true,
        supported: true,
    });
    s
}

// acceptance(spec = "desktop-app", scenario = "the menu bar says whether the daemon is running")
#[test]
fn a_running_daemon_is_named_with_its_port_and_version() {
    let s = running();
    assert_eq!(
        status_line(&s, Lang::En),
        "Daemon running · port 8000 · 0.4.2"
    );
    assert_eq!(icon(&s), Icon::Normal);
    assert_eq!(attention_label(&s, Lang::En), None);
    assert!(needs_daemon_enabled(&s));
    assert_eq!(login_item(&s), (true, true));
    assert_eq!(daemon_action(&s, Lang::En), "Restart daemon");
    assert_eq!(
        update_item(&s.update, Lang::En),
        ("Check for updates…".to_owned(), true)
    );
}

// acceptance(spec = "desktop-app", scenario = "the menu bar counts what needs the user")
#[test]
fn things_that_need_the_user_are_counted_and_dotted() {
    let mut s = running();
    s.attention = Attention {
        count: 2,
        only_kind: None,
    };
    assert_eq!(icon(&s), Icon::Attention);
    assert_eq!(
        attention_label(&s, Lang::En).as_deref(),
        Some("2 things need you")
    );
    assert_eq!(
        attention_label(&s, Lang::Zh).as_deref(),
        Some("2 件事需要你处理")
    );
    s.attention.count = 1;
    s.attention.only_kind = Some("mcp_server".into());
    assert_eq!(
        attention_label(&s, Lang::En).as_deref(),
        Some("1 thing needs you")
    );
}

#[test]
fn a_single_sync_problem_is_named_not_counted() {
    let mut s = running();
    s.sync_alert = Some("conflict".into());
    // Before the attention list has caught up with the alert…
    assert_eq!(icon(&s), Icon::Attention);
    let named = attention_label(&s, Lang::En).unwrap();
    assert!(named.starts_with("Sync needs attention"), "{named}");
    // …and once it lists the same one problem.
    s.attention = Attention {
        count: 1,
        only_kind: Some("sync".into()),
    };
    assert_eq!(attention_label(&s, Lang::En).unwrap(), named);
    // Two problems are counted, whichever they are.
    s.attention.count = 2;
    s.attention.only_kind = None;
    assert_eq!(
        attention_label(&s, Lang::En).as_deref(),
        Some("2 things need you")
    );
}

// acceptance(spec = "desktop-app", scenario = "an offline daemon greys out what needs it")
#[test]
fn offline_dims_the_icon_and_greys_out_what_needs_a_daemon() {
    let mut s = running();
    s.attention.count = 3;
    s.daemon = Daemon::Offline;
    assert_eq!(icon(&s), Icon::Offline);
    assert_eq!(status_line(&s, Lang::En), "Daemon offline");
    assert_eq!(attention_label(&s, Lang::En), None);
    assert!(!needs_daemon_enabled(&s));
    assert_eq!(
        login_item(&s),
        (false, true),
        "greyed, keeping the checkmark"
    );
    assert_eq!(daemon_action(&s, Lang::En), "Start daemon");
    // Checking for updates does not need a daemon.
    assert!(update_item(&s.update, Lang::En).1);
}

#[test]
fn a_launch_is_connecting_not_offline() {
    let s = TrayState::new(UpdateStatus::new("0.4.2", true));
    assert_eq!(status_line(&s, Lang::En), "Connecting to the daemon…");
    assert_eq!(icon(&s), Icon::Normal);
    assert_eq!(login_item(&s), (false, false));
}

// acceptance(spec = "desktop-app", scenario = "the menu bar offers an update that is ready")
#[test]
fn an_update_on_offer_replaces_check_for_updates() {
    let mut s = running();
    s.update.phase = Phase::Available;
    s.update.available = Some(AvailableUpdate {
        version: "0.4.3".into(),
        notes: None,
        date: None,
    });
    assert_eq!(
        update_item(&s.update, Lang::En),
        (
            "Update available — Restart to install 0.4.3".to_owned(),
            true
        )
    );
    // Busy states cannot be chosen twice.
    s.update.phase = Phase::Downloading;
    s.update.downloaded = Some(50);
    s.update.total = Some(200);
    assert_eq!(
        update_item(&s.update, Lang::En),
        ("Downloading update… 25%".to_owned(), false)
    );
    s.update.phase = Phase::Checking;
    assert!(!update_item(&s.update, Lang::En).1);
}

#[test]
fn a_platform_without_a_login_service_greys_start_at_login() {
    let mut s = running();
    s.login = Some(Login {
        installed: false,
        supported: false,
    });
    assert_eq!(login_item(&s), (false, false));
}

#[test]
fn the_tooltip_follows_the_icon() {
    let mut s = running();
    assert_eq!(tooltip(&s, Lang::En), "Coffer");
    s.attention.count = 1;
    assert_eq!(tooltip(&s, Lang::En), "Coffer — something needs you");
    s.daemon = Daemon::Offline;
    assert_eq!(tooltip(&s, Lang::Zh), "Coffer — 守护进程离线");
}
