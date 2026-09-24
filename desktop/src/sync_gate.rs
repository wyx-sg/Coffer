//! Whether the sync surfaces exist at all — the `vault_sync` experimental
//! feature (spec experimental-features "Close every surface of a switched-off
//! feature" and "Withdraw what a switched-off feature put in front of agents").
//!
//! While `vault_sync` is off the tray has no Sync entry, and the watcher neither
//! asks `/api/v1/sync/status` nor marks the tray, badges the Dock or raises a
//! notification. The feature switches live on the daemon, so the watcher reads
//! the daemon's unauthenticated status on a short tick and follows it: the entry
//! comes back and polling resumes on the first tick after it is switched on.
//!
//! Everything here is pure — `sync_watch.rs` does the reading and the effects,
//! the same split `sync_alert.rs` already has with it.

use std::time::Duration;

/// Read `features.vault_sync` from a `GET /api/v1/daemon/status` body.
///
/// `None` when the body is not a JSON object — that is "could not ask", which
/// leaves the tray as it is. A body with no `features` object, or one without
/// the key, is a daemon older than the feature registry, where sync was simply
/// always on: that reads as enabled.
pub fn parse_vault_sync(raw: &str) -> Option<bool> {
    let v: serde_json::Value = serde_json::from_str(raw).ok()?;
    let obj = v.as_object()?;
    Some(
        obj.get("features")
            .and_then(|f| f.get("vault_sync"))
            .and_then(serde_json::Value::as_bool)
            .unwrap_or(true),
    )
}

/// What the tray's Sync entry should do on this tick.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MenuChange {
    Show,
    Hide,
    Keep,
}

/// One tick's decision.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TickPlan {
    pub menu: MenuChange,
    /// Ask `/api/v1/sync/status` this tick.
    pub poll_sync: bool,
    /// Take down a mark that is showing (tray dot, Dock badge) because the
    /// feature it belongs to has been switched off.
    pub clear_marks: bool,
}

/// Decide one tick.
///
/// * `vault_sync` — the flag the daemon just reported.
/// * `item_shown` — whether the Sync entry is in the tray menu now.
/// * `marked` — whether an attention mark is showing now.
/// * `since_sync_poll` — time since the last sync poll, `None` if there has
///   been none since the feature was (last) switched on. A feature that has just
///   come on is therefore polled at once rather than a whole interval later.
pub fn plan_tick(
    vault_sync: bool,
    item_shown: bool,
    marked: bool,
    since_sync_poll: Option<Duration>,
    sync_interval: Duration,
) -> TickPlan {
    if !vault_sync {
        return TickPlan {
            menu: if item_shown {
                MenuChange::Hide
            } else {
                MenuChange::Keep
            },
            poll_sync: false,
            clear_marks: marked,
        };
    }
    TickPlan {
        menu: if item_shown {
            MenuChange::Keep
        } else {
            MenuChange::Show
        },
        poll_sync: since_sync_poll.is_none_or(|elapsed| elapsed >= sync_interval),
        clear_marks: false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEN_MIN: Duration = Duration::from_secs(600);

    // --- reading the daemon's status ---

    #[test]
    fn the_flag_is_read_from_the_features_object() {
        let off = r#"{"version":"0.5.0","channel":"stable",
                      "features":{"vault_sync":false,"knowledge":true,"memory":true}}"#;
        let on = r#"{"channel":"dev","features":{"vault_sync":true}}"#;
        assert_eq!(parse_vault_sync(off), Some(false));
        assert_eq!(parse_vault_sync(on), Some(true));
    }

    #[test]
    fn an_older_daemon_without_features_reads_as_enabled() {
        // Before the registry existed sync was always on; a new shell over an
        // old daemon must not hide a feature that daemon still serves.
        assert_eq!(parse_vault_sync(r#"{"version":"0.4.0"}"#), Some(true));
        assert_eq!(parse_vault_sync(r#"{"features":{}}"#), Some(true));
        assert_eq!(
            parse_vault_sync(r#"{"features":{"vault_sync":"yes"}}"#),
            Some(true)
        );
    }

    #[test]
    fn a_body_that_is_not_an_object_is_no_answer() {
        assert_eq!(parse_vault_sync("not json"), None);
        assert_eq!(parse_vault_sync("[]"), None);
        assert_eq!(parse_vault_sync(""), None);
    }

    // --- the tick decision ---

    #[test]
    fn switched_off_hides_the_item_and_never_polls() {
        for since in [None, Some(Duration::ZERO), Some(TEN_MIN * 10)] {
            let plan = plan_tick(false, true, false, since, TEN_MIN);
            assert_eq!(plan.menu, MenuChange::Hide);
            assert!(!plan.poll_sync);
        }
        assert_eq!(
            plan_tick(false, false, false, None, TEN_MIN).menu,
            MenuChange::Keep
        );
    }

    #[test]
    fn switched_off_takes_down_a_mark_that_is_showing() {
        assert!(plan_tick(false, true, true, None, TEN_MIN).clear_marks);
        assert!(!plan_tick(false, true, false, None, TEN_MIN).clear_marks);
        // Never while on: that is `sync_alert::next_action`'s call.
        assert!(!plan_tick(true, true, true, None, TEN_MIN).clear_marks);
    }

    #[test]
    fn switched_on_shows_the_item_and_polls_at_once() {
        let plan = plan_tick(true, false, false, None, TEN_MIN);
        assert_eq!(plan.menu, MenuChange::Show);
        assert!(plan.poll_sync);
    }

    #[test]
    fn while_on_the_sync_poll_keeps_its_own_slow_interval() {
        let recent = plan_tick(true, true, false, Some(Duration::from_secs(30)), TEN_MIN);
        assert_eq!(recent.menu, MenuChange::Keep);
        assert!(!recent.poll_sync);
        assert!(plan_tick(true, true, false, Some(TEN_MIN), TEN_MIN).poll_sync);
    }
}
