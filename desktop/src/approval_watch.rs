//! Tell the person when a secret is waiting for their approval (spec
//! desktop-app "Release plaintext and approvals only after a presence check in
//! the shell"; design D1 of `add-secret-boundary`).
//!
//! A request to send a secret somewhere new is held by the daemon until a
//! person approves it in this app. Nobody is looking at the page when an agent
//! asks, so every tick reads `daemon.json`, lists the pending approvals, and
//! raises ONE native notification per approval this process has not told the
//! person about yet — plus a `coffer://approvals` event, so an open page can
//! bring up its approval sheet. A tick that cannot reach the daemon changes
//! nothing: a restarting daemon is not news that the queue emptied.

use std::collections::HashSet;
use std::time::Duration;

use serde_json::Value;
use tauri::{AppHandle, Emitter};
use tauri_plugin_notification::NotificationExt;

use crate::daemon_http::fetch_ok;
use crate::discovery::read_daemon_info;
use crate::tray_locale::{self, Lang};

/// The event the page listens for to open its approval sheet.
pub const APPROVALS_EVENT: &str = "coffer://approvals";

/// A pending approval is someone waiting, so this is a short tick, not the
/// sync watcher's slow poll.
const TICK: Duration = Duration::from_secs(15);
/// Let the launch handshake's detect-or-spawn go first.
const FIRST_TICK_DELAY: Duration = Duration::from_secs(5);

const PENDING_PATH: &str = "/api/v1/secrets/approvals?status=pending";

/// One pending approval, as much of it as a notification needs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Pending {
    pub id: String,
    pub description: String,
}

/// Start watching. Runs forever on its own thread.
pub fn start(app: AppHandle) {
    std::thread::spawn(move || {
        let mut seen: HashSet<String> = HashSet::new();
        std::thread::sleep(FIRST_TICK_DELAY);
        loop {
            if let Some(pending) = read_pending() {
                let (fresh, next) = plan(&seen, &pending);
                seen = next;
                if !fresh.is_empty() {
                    announce(&app, &fresh);
                }
            }
            std::thread::sleep(TICK);
        }
    });
}

/// `None` for "could not ask" — never an answer about the queue.
fn read_pending() -> Option<Vec<Pending>> {
    let (port, token) = read_daemon_info()?;
    parse_pending(&fetch_ok(port, &token, PENDING_PATH)?)
}

/// The pending list from the daemon's answer. `None` when the answer is not
/// the shape this expects, which a tick treats like an unreachable daemon.
fn parse_pending(body: &str) -> Option<Vec<Pending>> {
    let v: Value = serde_json::from_str(body).ok()?;
    let list = v.get("approvals")?.as_array()?;
    Some(
        list.iter()
            .filter(|a| a.get("status").and_then(Value::as_str).unwrap_or("pending") == "pending")
            .filter_map(|a| {
                Some(Pending {
                    id: a.get("id")?.as_str()?.to_owned(),
                    description: a
                        .get("description")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_owned(),
                })
            })
            .collect(),
    )
}

/// Which approvals are new, and what to remember afterwards. Remembering only
/// the ids still pending keeps the set as small as the queue; an id is never
/// reused, so forgetting a settled one cannot re-announce it.
fn plan(seen: &HashSet<String>, pending: &[Pending]) -> (Vec<Pending>, HashSet<String>) {
    let fresh = pending
        .iter()
        .filter(|p| !seen.contains(&p.id))
        .cloned()
        .collect();
    let next = pending.iter().map(|p| p.id.clone()).collect();
    (fresh, next)
}

fn announce(app: &AppHandle, fresh: &[Pending]) {
    let lang = tray_locale::current();
    for approval in fresh {
        log::info!("approval.pending id={} notified", approval.id);
        if let Err(e) = app
            .notification()
            .builder()
            .title(notification_title(lang))
            .body(notification_body(&approval.description, lang))
            .show()
        {
            log::warn!("approval.pending notification failed: {e}");
        }
    }
    let ids: Vec<&str> = fresh.iter().map(|p| p.id.as_str()).collect();
    if let Err(e) = app.emit_to("main", APPROVALS_EVENT, serde_json::json!({ "ids": ids })) {
        log::warn!("approval.pending event failed: {e}");
    }
}

fn notification_title(lang: Lang) -> &'static str {
    match lang {
        Lang::En => "Coffer needs your approval",
        Lang::Zh => "Coffer 需要你批准",
    }
}

fn notification_body(description: &str, lang: Lang) -> String {
    let description = description.trim();
    if !description.is_empty() {
        return description.to_owned();
    }
    match lang {
        Lang::En => "A secret is waiting to be sent somewhere new.".to_owned(),
        Lang::Zh => "有一个密钥等待发送到新的位置。".to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pending(id: &str) -> Pending {
        Pending {
            id: id.into(),
            description: format!("send {id}"),
        }
    }

    // acceptance(spec = "desktop-app", scenario = "a pending approval raises one notification")
    #[test]
    fn a_pending_approval_is_announced_once() {
        let first = [pending("a")];
        let (fresh, seen) = plan(&HashSet::new(), &first);
        assert_eq!(fresh, vec![pending("a")]);

        // The next tick sees the same approval: nothing to say.
        let (fresh, seen) = plan(&seen, &first);
        assert!(fresh.is_empty());

        // A second one arrives beside it: only the newcomer is announced.
        let (fresh, seen) = plan(&seen, &[pending("a"), pending("b")]);
        assert_eq!(fresh, vec![pending("b")]);

        // Both settle; the memory shrinks with the queue.
        let (fresh, seen) = plan(&seen, &[]);
        assert!(fresh.is_empty());
        assert!(seen.is_empty());
    }

    #[test]
    fn the_pending_list_is_read_from_the_daemons_answer() {
        let body = r#"{"approvals":[
            {"id":"a1","op":"bind","status":"pending","description":"send gh/token to server gh"},
            {"id":"a2","status":"approved","description":"old"},
            {"status":"pending"}
        ]}"#;
        let list = parse_pending(body).unwrap();
        assert_eq!(
            list,
            vec![Pending {
                id: "a1".into(),
                description: "send gh/token to server gh".into()
            }]
        );
        // Not the expected shape: no answer, so the tick changes nothing.
        assert_eq!(parse_pending("{}"), None);
        assert_eq!(parse_pending("not json"), None);
    }

    #[test]
    fn a_notification_without_a_description_still_says_what_it_is() {
        assert_eq!(notification_body(" send x ", Lang::En), "send x");
        assert!(!notification_body("", Lang::En).is_empty());
        assert!(!notification_body("", Lang::Zh).is_empty());
    }
}
