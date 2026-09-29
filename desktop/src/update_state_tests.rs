//! Tests for `update_state.rs`: when the shell checks, and what each outcome
//! leaves on the About tab.

use super::*;

fn offer(version: &str) -> AvailableUpdate {
    AvailableUpdate {
        version: version.into(),
        notes: Some("Secrets have their own page.".into()),
        date: Some("2026-09-27T00:00:00Z".into()),
    }
}

// acceptance(spec = "desktop-app", scenario = "the shell checks at launch and every six hours")
#[test]
fn it_checks_at_launch_and_then_every_six_hours() {
    let launch = SystemTime::UNIX_EPOCH + Duration::from_secs(1_000_000);
    // Never checked: due at launch (after the short first delay).
    assert!(check_due(true, None, launch));
    assert!(FIRST_CHECK_DELAY < Duration::from_secs(120));
    // Not again until six hours have passed.
    assert!(!check_due(
        true,
        Some(launch),
        launch + Duration::from_secs(3600)
    ));
    assert!(!check_due(
        true,
        Some(launch),
        launch + CHECK_INTERVAL - Duration::from_secs(1)
    ));
    assert!(check_due(true, Some(launch), launch + CHECK_INTERVAL));
    assert_eq!(CHECK_INTERVAL, Duration::from_secs(6 * 60 * 60));
    // A clock that went backwards is not a reason to check in a loop.
    assert!(!check_due(
        true,
        Some(launch),
        launch - Duration::from_secs(60)
    ));
}

// acceptance(spec = "desktop-app", scenario = "the shell checks at launch and every six hours")
#[test]
fn a_check_records_what_it_found_and_installs_nothing() {
    let mut s = UpdateStatus::new("1.0.0", true);
    s.begin_check().unwrap();
    assert_eq!(s.phase, Phase::Checking);
    s.finish_check(42, Ok(Some(offer("1.0.1"))));
    assert_eq!(s.phase, Phase::Available);
    assert_eq!(s.last_checked_at, Some(42));
    assert_eq!(s.available.as_ref().unwrap().version, "1.0.1");
    // Nothing was downloaded: that takes the user's Download and restart.
    assert_eq!(s.downloaded, None);
    assert_eq!(s.current_version, "1.0.0");
}

#[test]
fn switching_automatic_checks_off_stops_the_timer_only() {
    let now = SystemTime::now();
    assert!(!check_due(false, None, now));
    let mut s = UpdateStatus::new("1.0.0", true);
    s.auto_check = false;
    // A check by hand still runs.
    assert!(s.begin_check().is_ok());
}

#[test]
fn a_build_without_an_update_key_never_checks() {
    let mut s = UpdateStatus::new("1.0.0", false);
    assert_eq!(s.begin_check().unwrap_err(), NOT_CONFIGURED);
    assert_eq!(s.phase, Phase::Idle);
}

#[test]
fn a_second_press_while_busy_is_refused() {
    let mut s = UpdateStatus::new("1.0.0", true);
    s.begin_check().unwrap();
    assert!(s.begin_check().is_err());
    assert!(s.begin_install().is_err());
}

#[test]
fn a_failed_check_keeps_the_last_good_result() {
    let mut s = UpdateStatus::new("1.0.0", true);
    s.begin_check().unwrap();
    s.finish_check(100, Ok(None));
    assert_eq!(s.phase, Phase::UpToDate);
    s.begin_check().unwrap();
    s.finish_check(200, Err(Failure::Network("timed out after 10 s".into())));
    assert_eq!(s.phase, Phase::Failed);
    assert_eq!(
        s.last_checked_at,
        Some(100),
        "the last SUCCESSFUL check's time"
    );
    assert!(s.error.as_deref().unwrap().contains("timed out after 10 s"));
    assert_eq!(s.current_version, "1.0.0");
}

// acceptance(spec = "desktop-app", scenario = "an update is installed only with a valid signature")
#[test]
fn a_refused_signature_installs_nothing_and_says_why() {
    let mut s = UpdateStatus::new("1.0.0", true);
    s.begin_check().unwrap();
    s.finish_check(1, Ok(Some(offer("1.0.1"))));
    s.begin_install().unwrap();
    s.progress(1024, Some(4096));
    s.install_failed(Failure::Signature("signature mismatch".into()));
    assert_eq!(s.phase, Phase::Failed);
    let error = s.error.clone().unwrap();
    assert!(error.contains("signature did not verify"), "{error}");
    assert!(error.contains("not installed"), "{error}");
    // Still running the version it was, still offering the update.
    assert_eq!(s.current_version, "1.0.0");
    assert_eq!(s.available.as_ref().unwrap().version, "1.0.1");
    assert_eq!((s.downloaded, s.total), (None, None));
}

#[test]
fn installing_needs_an_update_the_user_was_shown() {
    let mut s = UpdateStatus::new("1.0.0", true);
    assert!(s.begin_install().is_err());
    s.finish_check(1, Ok(Some(offer("1.0.1"))));
    s.begin_install().unwrap();
    assert_eq!(s.phase, Phase::Downloading);
    s.progress(10, Some(40));
    s.progress(10, None);
    assert_eq!((s.downloaded, s.total), (Some(20), Some(40)));
    s.installing();
    assert_eq!(s.phase, Phase::Installing);
}

#[test]
fn the_status_serialises_in_the_pages_terms() {
    let mut s = UpdateStatus::new("1.0.0", true);
    s.finish_check(5, Ok(Some(offer("1.0.1"))));
    let v = serde_json::to_value(&s).unwrap();
    assert_eq!(v["phase"], "available");
    assert_eq!(v["currentVersion"], "1.0.0");
    assert_eq!(v["lastCheckedAt"], 5);
    assert_eq!(v["available"]["version"], "1.0.1");
    assert_eq!(v["autoCheck"], true);
    let up_to_date = serde_json::to_value(Phase::UpToDate).unwrap();
    assert_eq!(up_to_date, "upToDate");
}
