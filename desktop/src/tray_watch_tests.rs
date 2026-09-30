//! Tests for `tray_watch.rs`: reading the daemon's answers, and when the menu
//! bar says offline.

use super::*;

#[test]
fn an_answer_is_running_with_its_port_and_version() {
    let d = next_daemon(&Daemon::Offline, Some((8123, "1.0.0".into())), 0);
    assert_eq!(
        d,
        Daemon::Running {
            port: 8123,
            version: "1.0.0".into()
        }
    );
}

#[test]
fn a_launch_allows_a_cold_daemon_a_few_probes() {
    assert_eq!(
        next_daemon(&Daemon::Connecting, None, 1),
        Daemon::Connecting
    );
    assert_eq!(
        next_daemon(&Daemon::Connecting, None, LAUNCH_GRACE_FAILURES),
        Daemon::Offline
    );
}

#[test]
fn a_daemon_that_stops_answering_is_offline_at_once() {
    let was = Daemon::Running {
        port: 8000,
        version: "1.0.0".into(),
    };
    assert_eq!(next_daemon(&was, None, 1), Daemon::Offline);
}

#[test]
fn the_status_version_is_read_and_absent_is_empty() {
    assert_eq!(parse_version(r#"{"version":"1.0.0","port":8000}"#), "1.0.0");
    assert_eq!(parse_version(r#"{"port":8000}"#), "");
    assert_eq!(parse_version("not json"), "");
}

#[test]
fn the_attention_list_is_counted_and_a_single_item_named() {
    let two =
        r#"{"items":[{"kind":"mcp_server"},{"kind":"sync"}],"errors":[],"counts_by_kind":{}}"#;
    assert_eq!(
        parse_attention(two),
        Some(Attention {
            count: 2,
            only_kind: None
        })
    );
    let one = r#"{"items":[{"kind":"sync","title":"Sync"}]}"#;
    assert_eq!(
        parse_attention(one).unwrap().only_kind.as_deref(),
        Some("sync")
    );
    assert_eq!(parse_attention(r#"{"items":[]}"#).unwrap().count, 0);
    // An unreadable answer is no answer, never "nothing needs you".
    assert_eq!(parse_attention("{}"), None);
    assert_eq!(parse_attention("oops"), None);
}

#[test]
fn the_login_service_is_read_from_residency() {
    let on = r#"{"login_service_installed":true,"login_service_supported":true}"#;
    assert_eq!(
        parse_login(on),
        Some(Login {
            installed: true,
            supported: true
        })
    );
    let unsupported = r#"{"login_service_installed":false,"login_service_supported":false}"#;
    assert!(!parse_login(unsupported).unwrap().supported);
    assert_eq!(parse_login("{}"), None);
    // The daemon always states whether a login service is supported; an
    // answer without it is not read as "supported".
    assert_eq!(parse_login(r#"{"login_service_installed":true}"#), None);
}

#[test]
fn the_status_tick_is_light_and_the_slow_reads_are_slower() {
    assert!(STATUS_TICK >= Duration::from_secs(5));
    assert!(SLOW_TICK > STATUS_TICK);
    assert!(FIRST_TICK_DELAY < STATUS_TICK);
}
