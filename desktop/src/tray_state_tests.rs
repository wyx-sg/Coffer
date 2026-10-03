//! Tests for `tray_state.rs`: the menu bar as the design canvas draws it
//! (1.3.01 Normal, 1.3.02 Needs you, 1.3.03 Daemon offline).

use super::*;

fn running() -> TrayState {
    let mut s = TrayState::new();
    s.daemon = Daemon::Running {
        port: 8000,
        version: "1.0.0".into(),
    };
    s
}

// acceptance(spec = "desktop-app", scenario = "the menu bar says whether the daemon is running")
#[test]
fn a_running_daemon_is_named_with_its_port_and_version() {
    let s = running();
    assert_eq!(
        status_line(&s, Lang::En),
        "Daemon running · port 8000 · 1.0.0"
    );
    assert_eq!(icon(&s), Icon::Normal);
    assert_eq!(title(&s), None);
    assert_eq!(attention_label(&s, Lang::En), None);
    assert_eq!(daemon_action(&s, Lang::En), "Restart daemon");
}

// acceptance(spec = "desktop-app", scenario = "the menu bar counts what needs the user")
#[test]
fn things_that_need_the_user_are_counted_beside_the_icon() {
    let mut s = running();
    s.attention = Attention { count: 9 };
    assert_eq!(icon(&s), Icon::Normal);
    assert_eq!(title(&s).as_deref(), Some("9"));
    assert_eq!(
        attention_label(&s, Lang::En).as_deref(),
        Some("9 things need you")
    );
    assert_eq!(
        attention_label(&s, Lang::Zh).as_deref(),
        Some("9 件事需要你处理")
    );
    s.attention.count = 1;
    assert_eq!(title(&s).as_deref(), Some("1"));
    assert_eq!(
        attention_label(&s, Lang::En).as_deref(),
        Some("1 thing needs you")
    );
}

// acceptance(spec = "desktop-app", scenario = "the count on the icon stops at 9+")
#[test]
fn a_count_past_nine_reads_nine_plus() {
    let mut s = running();
    s.attention = Attention { count: 10 };
    assert_eq!(title(&s).as_deref(), Some("9+"));
    // The menu line keeps the real number.
    assert_eq!(
        attention_label(&s, Lang::En).as_deref(),
        Some("10 things need you")
    );
}

#[test]
fn a_raised_sync_alert_counts_before_the_attention_list_catches_up() {
    let mut s = running();
    s.sync_alert = true;
    assert_eq!(title(&s).as_deref(), Some("1"));
    s.attention = Attention { count: 3 };
    assert_eq!(title(&s).as_deref(), Some("3"));
}

// acceptance(spec = "desktop-app", scenario = "an offline daemon offers to start")
#[test]
fn offline_dims_the_icon_drops_the_count_and_offers_start() {
    let mut s = running();
    s.attention = Attention { count: 3 };
    s.daemon = Daemon::Offline;
    assert_eq!(icon(&s), Icon::Offline);
    assert_eq!(status_line(&s, Lang::En), "Daemon offline");
    assert_eq!(title(&s), None);
    assert_eq!(attention_label(&s, Lang::En), None);
    assert_eq!(daemon_action(&s, Lang::En), "Start daemon");
}

#[test]
fn a_launch_is_connecting_not_offline() {
    let s = TrayState::new();
    assert_eq!(status_line(&s, Lang::En), "Connecting to the daemon…");
    assert_eq!(icon(&s), Icon::Normal);
    assert_eq!(title(&s), None);
}

#[test]
fn the_tooltip_follows_the_state() {
    let mut s = running();
    assert_eq!(tooltip(&s, Lang::En), "Coffer");
    s.attention.count = 1;
    assert_eq!(tooltip(&s, Lang::En), "Coffer — something needs you");
    s.daemon = Daemon::Offline;
    assert_eq!(tooltip(&s, Lang::Zh), "Coffer — 守护进程离线");
}
