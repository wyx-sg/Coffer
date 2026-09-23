//! Whether the vault's last sync round needs a human — and, if it does,
//! whether the user has already been told.
//!
//! Spec vault-sync "Say a vault needs a human where the user already is": a round that ended held
//! for confirmation, conflicted, or unable to push or run must say so where the user already is.
//! A held vault converges no further and backs nothing up, so a hold nobody
//! sees is an outage that looks like silence; the first one in the field stood
//! for four days because the only surface that mentioned it was the `/sync`
//! page, which nobody had open.
//!
//! Everything here is pure — no Tauri, no socket, no clock. `sync_watch.rs`
//! owns the poll that feeds it and the tray/dock/notification effects it
//! decides on, the same split `restart.rs` and `daemon.rs` already use.

/// The `ConvergeStatus` values (backend `domain/sync/convergence.py`) that mean
/// the round ended needing a person. `awaiting_join` is one: a machine that has
/// not joined its remote converges nothing until someone runs adopt. The other
/// three — `ok`, `no_change`, `disabled` — are a vault that is fine, and
/// `disabled` in particular is the ordinary state of a machine whose remote is
/// switched off, not a fault.
///
/// This list is a copy of a vocabulary the daemon owns, which is the same
/// arrangement `daemon.json`'s fields are already in (spec desktop-app "Read the
/// daemon's credentials from its discovery file"):
/// a change on either side is made on both — and on the CLI's
/// `_NEEDS_ATTENTION` and the web's `useSyncAttention.ts`, which list the same five.
pub const ATTENTION_STATUSES: [&str; 5] = [
    "conflict",
    "awaiting_confirmation",
    "push_failed",
    "failed",
    "awaiting_join",
];

/// The part of `GET /api/v1/sync/status` this shell reads: is a remote
/// configured at all, and how did the last round end.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SyncSnapshot {
    pub configured: bool,
    /// Whether that remote is switched ON. Read separately from `configured`
    /// because a disabled remote makes the daemon return a `disabled` round
    /// WITHOUT recording it, so `last_run` keeps whatever it last was. Without
    /// this a user who answers a held round by switching sync off instead of
    /// answering it would keep a marked icon and a badged Dock for ever.
    pub enabled: bool,
    /// `None` when no round has run yet — a configured remote that has not had
    /// its first round is not a fault.
    pub last_status: Option<String>,
}

/// Read a `SyncStatusOut` body. `None` for anything that is not that shape, so
/// a daemon speaking a version this shell does not understand leaves the
/// previous decision standing rather than clearing a real alert.
pub fn parse_sync_status(raw: &str) -> Option<SyncSnapshot> {
    let v: serde_json::Value = serde_json::from_str(raw).ok()?;
    let configured = v.get("configured")?.as_bool()?;
    // Absent or malformed reads as OFF, which is the quiet direction: a body
    // this shell cannot fully read must not be the thing that starts alerting.
    let enabled = v
        .get("remote")
        .and_then(|r| r.get("enabled"))
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false);
    let last_status = v
        .get("last_run")
        .and_then(|run| run.get("status"))
        .and_then(|s| s.as_str())
        .map(str::to_owned);
    Some(SyncSnapshot {
        configured,
        enabled,
        last_status,
    })
}

/// The status a snapshot needs a human for, or `None`.
///
/// An unconfigured vault is never one: sync being off is the ordinary state of
/// a fresh install, and the shell does nothing at all on those machines. It is
/// also the reason removing a remote *clears* an alert rather than freezing it
/// — the question the hold asked no longer has anyone to answer it.
///
/// A remote that is configured but **switched off** is the same answer for a
/// sharper reason. The daemon returns a `disabled` round without recording it,
/// so `last_run` keeps reporting whatever it last was; a user who meets a held
/// round by turning sync off rather than by answering it would otherwise carry
/// a marked tray icon and a badged Dock until they turned it back on.
pub fn attention_status(snapshot: &SyncSnapshot) -> Option<&str> {
    if !snapshot.configured || !snapshot.enabled {
        return None;
    }
    let status = snapshot.last_status.as_deref()?;
    ATTENTION_STATUSES.contains(&status).then_some(status)
}

/// What the shell should do on one poll, given what it last notified about.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AlertAction {
    /// Mark the icon and raise one notification for this status.
    Raise(String),
    /// Un-mark the icon; the condition is gone.
    Clear,
    /// Leave every surface exactly as it is.
    Nothing,
}

/// The whole "notify once per transition" rule.
///
/// `notified` is the status the last raised notification was about, or `None`
/// if the shell is not currently marking anything. Keying on the *status* and
/// not on a bare "alerting" flag is deliberate: a vault that goes from
/// `push_failed` to `conflict` has a different problem and deserves to be told
/// again, while a vault that is still `awaiting_confirmation` an hour later has
/// the same one and must not be nagged for it. A user who has been told and has
/// not acted is not told again until the condition clears and returns.
pub fn next_action(notified: Option<&str>, snapshot: &SyncSnapshot) -> AlertAction {
    match (attention_status(snapshot), notified) {
        (Some(now), Some(before)) if now == before => AlertAction::Nothing,
        (Some(now), _) => AlertAction::Raise(now.to_owned()),
        (None, Some(_)) => AlertAction::Clear,
        (None, None) => AlertAction::Nothing,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A remote that is configured is also switched ON, which is what every
    /// case below but the two that say otherwise means. The off case has its
    /// own constructor rather than a third argument on twenty call sites.
    fn snapshot(configured: bool, status: Option<&str>) -> SyncSnapshot {
        SyncSnapshot {
            configured,
            enabled: configured,
            last_status: status.map(str::to_owned),
        }
    }

    /// Configured, and switched off.
    fn switched_off(status: Option<&str>) -> SyncSnapshot {
        SyncSnapshot {
            configured: true,
            enabled: false,
            last_status: status.map(str::to_owned),
        }
    }

    // --- reading the daemon's answer ---

    #[test]
    fn a_remote_switched_off_parses_as_not_enabled() {
        let raw = r#"{"configured": true,
                      "remote": {"url": "git@example:v.git", "enabled": false},
                      "last_run": {"status": "awaiting_confirmation", "applied": {}},
                      "machine_id": "m1", "machine_id_is_derived": false}"#;
        assert_eq!(
            parse_sync_status(raw),
            Some(switched_off(Some("awaiting_confirmation")))
        );
    }

    #[test]
    fn a_body_without_the_enabled_field_reads_as_off() {
        // The quiet direction. A body this shell cannot fully read must not be
        // the thing that starts alerting.
        let raw = r#"{"configured": true, "remote": {"url": "u"},
                      "last_run": {"status": "failed"},
                      "machine_id": "m1", "machine_id_is_derived": false}"#;
        assert_eq!(parse_sync_status(raw).map(|s| s.enabled), Some(false));
    }

    #[test]
    fn parse_sync_status_reads_configured_and_last_status() {
        let raw = r#"{"configured": true,
                      "remote": {"url": "git@example:v.git", "enabled": true},
                      "last_run": {"status": "awaiting_confirmation", "applied": {}},
                      "machine_id": "m1", "machine_id_is_derived": false}"#;
        assert_eq!(
            parse_sync_status(raw),
            Some(snapshot(true, Some("awaiting_confirmation")))
        );
    }

    #[test]
    fn parse_sync_status_handles_a_remote_that_has_never_run() {
        let raw = r#"{"configured": true, "remote": {"enabled": true}, "last_run": null,
                      "machine_id": "m1", "machine_id_is_derived": false}"#;
        assert_eq!(parse_sync_status(raw), Some(snapshot(true, None)));
    }

    #[test]
    fn parse_sync_status_handles_an_unconfigured_vault() {
        let raw = r#"{"configured": false, "remote": null, "last_run": null,
                      "machine_id": "m1", "machine_id_is_derived": true}"#;
        assert_eq!(parse_sync_status(raw), Some(snapshot(false, None)));
    }

    #[test]
    fn parse_sync_status_rejects_anything_that_is_not_that_shape() {
        assert_eq!(parse_sync_status("not json"), None);
        assert_eq!(parse_sync_status("{}"), None);
        assert_eq!(parse_sync_status(r#"{"configured": "yes"}"#), None);
    }

    // --- which statuses are a fault ---

    #[test]
    fn every_attention_status_is_a_fault() {
        for status in ATTENTION_STATUSES {
            assert_eq!(
                attention_status(&snapshot(true, Some(status))),
                Some(status),
                "{status} should need a human"
            );
        }
    }

    #[test]
    fn a_machine_that_has_not_joined_needs_a_human() {
        // The CLI (`_NEEDS_ATTENTION`) and the web (`useSyncAttention.ts`) both
        // count it: every round converges nothing until someone runs adopt.
        assert_eq!(
            attention_status(&snapshot(true, Some("awaiting_join"))),
            Some("awaiting_join")
        );
        assert_eq!(
            next_action(None, &snapshot(true, Some("awaiting_join"))),
            AlertAction::Raise("awaiting_join".into())
        );
    }

    #[test]
    fn a_healthy_round_is_not_a_fault() {
        for status in ["ok", "no_change", "disabled"] {
            assert_eq!(attention_status(&snapshot(true, Some(status))), None);
        }
        assert_eq!(attention_status(&snapshot(true, None)), None);
    }

    #[test]
    fn an_unconfigured_vault_is_never_a_fault() {
        // Rule 5 of the brief, and the reason a fresh install sees nothing:
        // even a stale `failed` round on a vault with no remote is not a
        // question anyone can answer.
        assert_eq!(attention_status(&snapshot(false, Some("failed"))), None);
    }

    #[test]
    fn a_remote_switched_off_is_never_an_attention_state() {
        // The bug this closes: a disabled remote makes the daemon return a
        // `disabled` round WITHOUT recording it, so `last_run` keeps whatever
        // it last was. A user who met a held round by switching sync off
        // rather than by answering it kept a marked tray icon and a badged
        // Dock until they switched it back on.
        for status in ATTENTION_STATUSES {
            assert_eq!(attention_status(&switched_off(Some(status))), None);
        }
        // And an alert already raised is CLEARED rather than frozen.
        assert_eq!(
            next_action(
                Some("awaiting_confirmation"),
                &switched_off(Some("awaiting_confirmation"))
            ),
            AlertAction::Clear
        );
    }

    // --- the state machine: one notification per transition ---

    #[test]
    fn a_new_condition_raises() {
        assert_eq!(
            next_action(None, &snapshot(true, Some("conflict"))),
            AlertAction::Raise("conflict".into())
        );
    }

    /// The load-bearing one. A user who has been told and has not acted must
    /// not be told again on the next tick — however many ticks later — or the
    /// poll becomes an hourly nag and the notification stops meaning anything.
    #[test]
    fn the_same_condition_on_the_next_poll_does_nothing() {
        let held = snapshot(true, Some("awaiting_confirmation"));
        for _ in 0..100 {
            assert_eq!(
                next_action(Some("awaiting_confirmation"), &held),
                AlertAction::Nothing
            );
        }
    }

    #[test]
    fn a_condition_that_clears_unmarks_the_icon() {
        assert_eq!(
            next_action(Some("conflict"), &snapshot(true, Some("ok"))),
            AlertAction::Clear
        );
    }

    #[test]
    fn a_condition_that_clears_and_returns_notifies_again() {
        // told → resolved → broken again. The second break is news.
        let mut notified: Option<String> = None;
        let mut seen = Vec::new();
        for status in ["conflict", "conflict", "ok", "ok", "conflict"] {
            let action = next_action(notified.as_deref(), &snapshot(true, Some(status)));
            match &action {
                AlertAction::Raise(s) => notified = Some(s.clone()),
                AlertAction::Clear => notified = None,
                AlertAction::Nothing => {}
            }
            seen.push(action);
        }
        assert_eq!(
            seen,
            vec![
                AlertAction::Raise("conflict".into()),
                AlertAction::Nothing,
                AlertAction::Clear,
                AlertAction::Nothing,
                AlertAction::Raise("conflict".into()),
            ]
        );
    }

    #[test]
    fn a_different_condition_notifies_even_without_clearing_first() {
        // `push_failed` becoming `conflict` is a different problem with a
        // different answer, so the user hears about it.
        assert_eq!(
            next_action(Some("push_failed"), &snapshot(true, Some("conflict"))),
            AlertAction::Raise("conflict".into())
        );
    }

    #[test]
    fn a_healthy_vault_nobody_was_warned_about_changes_nothing() {
        assert_eq!(
            next_action(None, &snapshot(true, Some("no_change"))),
            AlertAction::Nothing
        );
        assert_eq!(
            next_action(None, &snapshot(false, None)),
            AlertAction::Nothing
        );
    }

    #[test]
    fn removing_the_remote_clears_an_outstanding_mark() {
        assert_eq!(
            next_action(
                Some("awaiting_confirmation"),
                &snapshot(false, Some("awaiting_confirmation"))
            ),
            AlertAction::Clear
        );
    }

    // --- what the user reads ---

    // --- the icon mark ---
}
