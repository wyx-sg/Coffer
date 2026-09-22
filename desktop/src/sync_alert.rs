//! Whether the vault's last sync round needs a human — and, if it does,
//! whether the user has already been told.
//!
//! Spec vault-sync FR-096: a round that ended held for confirmation,
//! conflicted, or unable to push or run must say so where the user already is.
//! A held vault converges no further and backs nothing up, so a hold nobody
//! sees is an outage that looks like silence; the first one in the field stood
//! for four days because the only surface that mentioned it was the `/sync`
//! page, which nobody had open.
//!
//! Everything here is pure — no Tauri, no socket, no clock. `sync_watch.rs`
//! owns the poll that feeds it and the tray/dock/notification effects it
//! decides on, the same split `restart.rs` and `daemon.rs` already use.

/// The `ConvergeStatus` values (backend `domain/sync/convergence.py`) that mean
/// the round ended needing a person. The other three — `ok`, `no_change`,
/// `disabled` — are a vault that is fine, and `disabled` in particular is the
/// ordinary state of a machine whose remote is switched off, not a fault.
///
/// This list is a copy of a vocabulary the daemon owns, which is the same
/// arrangement `daemon.json`'s fields are already in (spec desktop-app FR-005):
/// a change on either side is made on both.
pub const ATTENTION_STATUSES: [&str; 4] =
    ["conflict", "awaiting_confirmation", "push_failed", "failed"];

/// The part of `GET /api/v1/sync/status` this shell reads: is a remote
/// configured at all, and how did the last round end.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SyncSnapshot {
    pub configured: bool,
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
    let last_status = v
        .get("last_run")
        .and_then(|run| run.get("status"))
        .and_then(|s| s.as_str())
        .map(str::to_owned);
    Some(SyncSnapshot {
        configured,
        last_status,
    })
}

/// The status a snapshot needs a human for, or `None`.
///
/// An unconfigured vault is never one: sync being off is the ordinary state of
/// a fresh install, and the shell does nothing at all on those machines. It is
/// also the reason removing a remote *clears* an alert rather than freezing it
/// — the question the hold asked no longer has anyone to answer it.
pub fn attention_status(snapshot: &SyncSnapshot) -> Option<&str> {
    if !snapshot.configured {
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

/// One line, naming the product: it arrives in Notification Centre beside
/// everything else on the machine.
pub const NOTIFICATION_TITLE: &str = "Coffer sync needs you";

/// What went wrong, in the terms the user has to act in. Each says what has
/// stopped as well as what happened — "held" means nothing else will converge,
/// and that is the part that cost four days.
pub fn notification_body(status: &str) -> &'static str {
    match status {
        "awaiting_confirmation" => {
            "A round is held for your confirmation. The vault will not converge \
             again until you answer it."
        }
        "conflict" => {
            "A round hit a conflict nothing could resolve. The vault is \
             untouched and sync is stopped until you resolve it."
        }
        "push_failed" => {
            "A round applied locally but could not push. This machine's \
             changes are not on the remote yet."
        }
        "failed" => "The last round failed to run. The vault has stopped converging.",
        // Unreachable through `next_action`, which only raises on the four
        // above; a default keeps a daemon that grew a fifth status from being
        // reported as nothing at all.
        _ => "The last round needs your attention before sync can continue.",
    }
}

/// The tray entry's label while a condition is outstanding. Short — it sits in
/// a menu — and it names the condition, so the tray answers "which problem"
/// without the window being opened.
pub fn tray_label(status: &str) -> String {
    let reason = match status {
        "awaiting_confirmation" => "held for confirmation",
        "conflict" => "conflict",
        "push_failed" => "push failed",
        "failed" => "run failed",
        _ => status,
    };
    format!("Sync needs attention — {reason}")
}

/// The alert dot: a red disc inside a white ring, so it reads against both a
/// light and a dark menu bar.
const BADGE_FILL: [u8; 4] = [0xE5, 0x48, 0x4D, 0xFF];
const BADGE_RING: [u8; 4] = [0xFF, 0xFF, 0xFF, 0xFF];

/// Paint the alert dot into the bottom-right of a straight-RGBA image.
///
/// Badging the icon the app already has beats shipping a second `.png`: the two
/// cannot drift, and the mark lands in the same place whatever the base icon
/// becomes. A buffer whose length does not match its declared size is returned
/// untouched — a marked icon is worth having, a panicked tray thread is not.
pub fn badge_rgba(rgba: &[u8], width: u32, height: u32) -> Vec<u8> {
    let expected = (width as usize) * (height as usize) * 4;
    if rgba.len() != expected || width == 0 || height == 0 {
        return rgba.to_vec();
    }
    let mut out = rgba.to_vec();

    // Three-sixteenths of the shorter side, floored at 2px: big enough to see
    // in a 16pt menu bar, small enough to leave the icon recognisable.
    let radius = ((width.min(height) * 3) / 16).max(2) as i64;
    let ring = radius + (radius / 4).max(1);
    let cx = width as i64 - ring - 1;
    let cy = height as i64 - ring - 1;

    for y in 0..height as i64 {
        for x in 0..width as i64 {
            let d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy);
            let colour = if d2 <= radius * radius {
                BADGE_FILL
            } else if d2 <= ring * ring {
                BADGE_RING
            } else {
                continue;
            };
            let i = ((y as usize) * (width as usize) + (x as usize)) * 4;
            out[i..i + 4].copy_from_slice(&colour);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snapshot(configured: bool, status: Option<&str>) -> SyncSnapshot {
        SyncSnapshot {
            configured,
            last_status: status.map(str::to_owned),
        }
    }

    // --- reading the daemon's answer ---

    #[test]
    fn parse_sync_status_reads_configured_and_last_status() {
        let raw = r#"{"configured": true, "remote": {"url": "git@example:v.git"},
                      "last_run": {"status": "awaiting_confirmation", "applied": {}},
                      "machine_id": "m1", "machine_id_is_derived": false}"#;
        assert_eq!(
            parse_sync_status(raw),
            Some(snapshot(true, Some("awaiting_confirmation")))
        );
    }

    #[test]
    fn parse_sync_status_handles_a_remote_that_has_never_run() {
        let raw = r#"{"configured": true, "remote": {}, "last_run": null,
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
    fn the_four_attention_statuses_are_faults() {
        for status in ATTENTION_STATUSES {
            assert_eq!(
                attention_status(&snapshot(true, Some(status))),
                Some(status),
                "{status} should need a human"
            );
        }
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

    #[test]
    fn every_attention_status_has_its_own_body_and_label() {
        let mut bodies: Vec<&str> = ATTENTION_STATUSES
            .iter()
            .map(|s| notification_body(s))
            .collect();
        assert!(bodies.iter().all(|b| !b.is_empty()));
        bodies.sort_unstable();
        bodies.dedup();
        assert_eq!(
            bodies.len(),
            ATTENTION_STATUSES.len(),
            "two statuses share a body"
        );

        for status in ATTENTION_STATUSES {
            let label = tray_label(status);
            assert!(label.starts_with("Sync needs attention — "), "{label}");
            // The raw enum name never reaches the menu.
            assert!(!label.contains('_'), "{label}");
        }
    }

    // --- the icon mark ---

    #[test]
    fn badge_rgba_paints_the_dot_in_the_bottom_right() {
        let base = vec![0x11u8; 32 * 32 * 4];
        let marked = badge_rgba(&base, 32, 32);
        assert_eq!(marked.len(), base.len());
        // Top-left is as far from the badge as a pixel gets: untouched.
        assert_eq!(&marked[0..4], &[0x11, 0x11, 0x11, 0x11]);
        // radius = 32*3/16 = 6, ring = 6 + 1 = 7, centre = (24, 24).
        let at = |x: usize, y: usize| &marked[(y * 32 + x) * 4..(y * 32 + x) * 4 + 4];
        assert_eq!(at(24, 24), BADGE_FILL, "centre should be the alert fill");
        assert_eq!(at(24, 31), BADGE_RING, "the ring should surround the fill");
    }

    #[test]
    fn badge_rgba_never_writes_outside_the_buffer_it_was_given() {
        // Declared 32x32 but four pixels long — returned, not panicked on.
        let short = vec![0u8; 16];
        assert_eq!(badge_rgba(&short, 32, 32), short);
        assert_eq!(badge_rgba(&[], 0, 0), Vec::<u8>::new());
        // A 4x4 icon: the radius floors at 2 and every write stays in bounds.
        assert_eq!(badge_rgba(&[0u8; 64], 4, 4).len(), 64);
    }
}
