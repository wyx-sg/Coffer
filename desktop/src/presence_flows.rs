//! The presence-checked flows, shared by the page's buttons (the IPC commands
//! in `secrets.rs`) and the command line's requests (`desktop_requests.rs`):
//! reveal a secret, approve one approval, approve several (spec desktop-app
//! "Release plaintext and approvals only after a presence check in the shell"
//! and "Serve the command line's desktop requests").
//!
//! Each reads what it is about from the daemon itself — never from whoever
//! asked — shows the operating system's prompt naming it, and only then asks
//! for a challenge and signs. A single approval's grant is pinned to the target
//! the person was shown (`<id>@<fingerprint>`, design D9 of
//! `align-cli-with-ui-and-add-tool-environments`): the daemon applies it only
//! while the approval still names that target. A caller may pin the target it
//! expects as well (the command line pins what it asked for); a target that
//! moved since is refused before any prompt.

use std::collections::HashMap;

use serde_json::{json, Value};
use tauri::AppHandle;

use crate::daemon_client::{path_segment, Daemon};
use crate::daemon_http::DEFAULT_READ_TIMEOUT;
use crate::presence::{self, Subject};
use crate::presence_grant::{self, GrantOp};

/// Reveal one secret to the person; the value goes back to the caller in this
/// process, which shows it in the window and keeps it nowhere.
pub fn reveal(
    app: &AppHandle,
    daemon: &Daemon,
    development: bool,
    secret_ref: &str,
) -> Result<String, String> {
    presence::confirm(app, &Subject::Reveal { secret_ref }, development)?;
    let (nonce, signature) = daemon.grant(GrantOp::Reveal, secret_ref)?;
    let answer = daemon.post(
        "/api/v1/secrets/presence/reveal",
        &json!({"ref": secret_ref, "nonce": nonce, "signature": signature}),
        DEFAULT_READ_TIMEOUT,
    )?;
    answer
        .get("value")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| "the daemon's answer carried no value".to_owned())
}

fn text(approval: &Value, name: &str) -> String {
    approval
        .get(name)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

/// The target a single approval's grant is signed over (the daemon's
/// `pinned_target`).
pub fn pinned_target(id: &str, fingerprint: &str) -> String {
    format!("{id}@{fingerprint}")
}

/// Approve one approval after its own presence check, pinned to its target.
pub fn approve_one(
    app: &AppHandle,
    daemon: &Daemon,
    development: bool,
    id: &str,
    expected: Option<&str>,
) -> Result<Value, String> {
    let path = format!("/api/v1/secrets/approvals/{}", path_segment(id)?);
    let approval = daemon.get(&path)?;
    if approval.get("status").and_then(Value::as_str) != Some("pending") {
        return Err(format!("approval {id} is no longer waiting"));
    }
    let fingerprint = text(&approval, "target_fingerprint");
    if let Some(expected) = expected {
        if expected != fingerprint {
            return Err(format!(
                "approval {id} now names another target than the one asked for; nothing was approved"
            ));
        }
    }
    let description = text(&approval, "description");
    presence::confirm(
        app,
        &Subject::Approve {
            id,
            description: &description,
        },
        development,
    )?;
    let (nonce, signature) = daemon.grant(GrantOp::Approve, &pinned_target(id, &fingerprint))?;
    daemon.post(
        &format!("{path}/approve"),
        &json!({"nonce": nonce, "signature": signature, "fingerprint": fingerprint}),
        DEFAULT_READ_TIMEOUT,
    )
}

/// Approve several under one presence check and one grant over a digest of
/// exactly the `(id, fingerprint)` pairs shown. An approval gone, no longer
/// pending, not batchable, or (with `expected`) naming another target than the
/// one asked for is left out, and the daemon reports it skipped.
pub fn approve_batch(
    app: &AppHandle,
    daemon: &Daemon,
    development: bool,
    ids: &[String],
    expected: Option<&HashMap<String, String>>,
) -> Result<Value, String> {
    let mut items: Vec<(String, String)> = Vec::new();
    let mut descriptions: Vec<String> = Vec::new();
    for id in ids {
        let approval = daemon.get(&format!("/api/v1/secrets/approvals/{}", path_segment(id)?))?;
        if !is_batchable(&approval) {
            continue;
        }
        let fingerprint = text(&approval, "target_fingerprint");
        if expected.is_some_and(|pins| pins.get(id) != Some(&fingerprint)) {
            continue;
        }
        items.push((id.clone(), fingerprint));
        descriptions.push(text(&approval, "description"));
    }
    if items.is_empty() {
        return Err("nothing in the selection is still waiting for approval".to_owned());
    }
    presence::confirm(
        app,
        &Subject::ApproveBatch {
            descriptions: &descriptions,
        },
        development,
    )?;
    let target = presence_grant::batch_target(&items);
    let (nonce, signature) = daemon.grant(GrantOp::ApproveBatch, &target)?;
    let listed: Vec<Value> = items
        .iter()
        .map(|(id, fingerprint)| json!({"id": id, "fingerprint": fingerprint}))
        .collect();
    daemon.post(
        "/api/v1/secrets/approvals/approve",
        &json!({"items": listed, "nonce": nonce, "signature": signature}),
        DEFAULT_READ_TIMEOUT,
    )
}

/// Whether an approval read from the daemon can be one of several: it waits,
/// it is not the switch that turns the protection off, and it is not a grant to
/// local programs (which an agent can start, so each takes its own prompt).
pub fn is_batchable(approval: &Value) -> bool {
    approval.get("status").and_then(Value::as_str) == Some("pending")
        && approval.get("op").and_then(Value::as_str) != Some("disable_protection")
        && approval.get("destination_kind").and_then(Value::as_str) != Some("local_process")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_a_waiting_approval_that_is_not_the_protection_switch_is_batchable() {
        let a = |status: &str, op: &str| json!({"status": status, "op": op});
        assert!(is_batchable(&a("pending", "bind")));
        assert!(is_batchable(&a("pending", "replace_value")));
        assert!(!is_batchable(&a("pending", "disable_protection")));
        let local = json!({"status": "pending", "op": "bind", "destination_kind": "local_process"});
        assert!(!is_batchable(&local));
        assert!(!is_batchable(&a("superseded", "bind")));
        assert!(!is_batchable(&json!({})));
    }

    /// The layout the daemon's `pinned_target` builds, byte for byte.
    // acceptance(spec = "secret", scenario = "a moved target or a replayed grant approves nothing")
    #[test]
    fn a_pinned_target_names_the_approval_and_its_target() {
        assert_eq!(
            pinned_target("0123456789abcdef", "fp1"),
            "0123456789abcdef@fp1"
        );
        assert_ne!(pinned_target("a", "fp1"), pinned_target("a", "fp2"));
    }
}
