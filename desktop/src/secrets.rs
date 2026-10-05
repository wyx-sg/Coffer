//! The IPC commands behind the secret boundary (spec desktop-app "Release
//! plaintext and approvals only after a presence check in the shell"; design
//! D1 of `add-secret-boundary`).
//!
//! Each command runs the same four steps in the same order: a presence check
//! whose prompt names the operation and its target, a challenge from the
//! daemon, a signature over exactly that operation, and the operation's own
//! request carrying `{nonce, signature}`. A cancelled or failed check sends
//! nothing. The master key is read for the signature and dropped with it.
//!
//! The commands are `async` and do their blocking work — the wait on the
//! person, the loopback requests — on Tauri's blocking pool, so the window
//! never freezes behind a Touch ID prompt.

use std::time::Duration;

use serde_json::{json, Value};
use tauri::AppHandle;

use crate::daemon_attest;
use crate::daemon_http::{self, DEFAULT_READ_TIMEOUT};
use crate::discovery::read_daemon_info;
use crate::master_key;
use crate::presence::{self, Subject};
use crate::presence_grant::{self, GrantOp};

/// The folder picker waits on a person choosing a folder in a native dialog.
const PICK_FOLDER_TIMEOUT: Duration = Duration::from_secs(600);
/// Writing the backup file is quick, but it is a disk write behind a request.
const EXPORT_TIMEOUT: Duration = Duration::from_secs(30);
/// The daemon refuses a shorter backup passphrase; checking here first spares
/// the person a Touch ID prompt that could only end in that refusal.
const MIN_PASSPHRASE_CHARS: usize = 8;

#[derive(serde::Serialize)]
pub struct MasterKeyBackup {
    pub path: String,
    pub fingerprint: String,
}

/// Show a secret's value to the person at the window. The page uses the
/// returned value for show/copy and keeps it nowhere.
#[tauri::command]
pub async fn reveal_secret(app: AppHandle, secret_ref: String) -> Result<String, String> {
    blocking(move || {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        presence::confirm(
            &app,
            &Subject::Reveal {
                secret_ref: &secret_ref,
            },
            development,
        )?;
        let (nonce, signature) = daemon.grant(GrantOp::Reveal, &secret_ref)?;
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
    })
    .await
}

/// Write a passphrase-protected backup of the master key (`coffer-master-key.cfk`)
/// into a folder the person picks. The presence check comes before the picker:
/// the folder is only asked for once a person has said they mean to export the
/// key at all. The passphrase the page collected goes to the daemon in the
/// export request and nowhere else — it is not logged, kept, or part of the
/// signed grant.
#[tauri::command]
pub async fn export_master_key_backup(
    app: AppHandle,
    passphrase: String,
) -> Result<MasterKeyBackup, String> {
    if passphrase.chars().count() < MIN_PASSPHRASE_CHARS {
        return Err(format!(
            "the passphrase must be at least {MIN_PASSPHRASE_CHARS} characters"
        ));
    }
    blocking(move || {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        presence::confirm(&app, &Subject::ExportMasterKey, development)?;
        let picked = daemon.post(
            "/api/v1/fs/pick-folder",
            &json!({"start": null}),
            PICK_FOLDER_TIMEOUT,
        )?;
        let directory = picked_folder(&picked)?;
        let (nonce, signature) = daemon.grant(GrantOp::ExportMasterKey, &directory)?;
        let written = daemon.post(
            "/api/v1/secrets/presence/master-key-export",
            &json!({
                "directory": directory,
                "passphrase": passphrase,
                "nonce": nonce,
                "signature": signature,
            }),
            EXPORT_TIMEOUT,
        )?;
        let field = |name: &str| {
            written
                .get(name)
                .and_then(Value::as_str)
                .map(str::to_owned)
                .ok_or_else(|| format!("the daemon's answer carried no {name}"))
        };
        Ok(MasterKeyBackup {
            path: field("path")?,
            fingerprint: field("fingerprint")?,
        })
    })
    .await
}

/// Approve a pending request (a secret about to go somewhere new). The prompt
/// carries the daemon's own description of the request, so the person reads
/// what is being approved in the operating system's dialog.
#[tauri::command]
pub async fn approve_pending(app: AppHandle, approval_id: String) -> Result<Value, String> {
    blocking(move || {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        let path = format!("/api/v1/secrets/approvals/{}", path_segment(&approval_id)?);
        let approval = daemon.get(&path)?;
        let description = approval
            .get("description")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let subject = Subject::Approve {
            id: &approval_id,
            description,
        };
        presence::confirm(&app, &subject, development)?;
        let (nonce, signature) = daemon.grant(GrantOp::Approve, &approval_id)?;
        daemon.post(
            &format!("{path}/approve"),
            &json!({"nonce": nonce, "signature": signature}),
            DEFAULT_READ_TIMEOUT,
        )
    })
    .await
}

/// Approve several pending requests under one presence check and one grant.
///
/// The shell, not the page, decides what is approved: it reads each approval
/// from the daemon (what it is and the target it is pinned to), keeps those
/// still pending and batchable, shows their descriptions in the prompt, and
/// signs the grant over a digest of exactly that list. The daemon recomputes
/// the digest from the list it is sent and applies only items still pending for
/// the same target. Ids that are gone or no longer pending are left out of the
/// list and so are reported by the page as skipped.
#[tauri::command]
pub async fn approve_pending_batch(
    app: AppHandle,
    approval_ids: Vec<String>,
) -> Result<Value, String> {
    blocking(move || {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        let mut items: Vec<(String, String)> = Vec::new();
        let mut descriptions: Vec<String> = Vec::new();
        for id in &approval_ids {
            let approval =
                daemon.get(&format!("/api/v1/secrets/approvals/{}", path_segment(id)?))?;
            if !is_batchable(&approval) {
                continue;
            }
            let text = |name: &str| {
                approval
                    .get(name)
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_owned()
            };
            items.push((id.clone(), text("target_fingerprint")));
            descriptions.push(text("description"));
        }
        if items.is_empty() {
            return Err("nothing in the selection is still waiting for approval".to_owned());
        }
        presence::confirm(
            &app,
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
    })
    .await
}

/// Whether an approval read from the daemon can be one of several: it waits,
/// it is not the switch that turns the protection off, and it is not a grant to
/// local programs (which an agent can start, so each takes its own prompt).
fn is_batchable(approval: &Value) -> bool {
    approval.get("status").and_then(Value::as_str) == Some("pending")
        && approval.get("op").and_then(Value::as_str) != Some("disable_protection")
        && approval.get("destination_kind").and_then(Value::as_str) != Some("local_process")
}

/// Run blocking work on Tauri's blocking pool.
pub(crate) async fn blocking<T, F>(work: F) -> Result<T, String>
where
    F: FnOnce() -> Result<T, String> + Send + 'static,
    T: Send + 'static,
{
    tauri::async_runtime::spawn_blocking(work)
        .await
        .map_err(|e| format!("the operation stopped unexpectedly: {e}"))?
}

/// The running daemon, as `daemon.json` names it.
pub(crate) struct Daemon {
    port: u16,
    token: String,
}

impl Daemon {
    pub(crate) fn find() -> Result<Daemon, String> {
        let (port, token) = read_daemon_info().ok_or("Coffer's daemon is not running")?;
        // Before anything is sent: `daemon.json` can be written by any process
        // of this user, so the daemon it names must first prove it holds the key.
        daemon_attest::verify_daemon(port, &token)?;
        Ok(Daemon { port, token })
    }

    fn get(&self, path: &str) -> Result<Value, String> {
        daemon_http::json_or_error(daemon_http::get(
            self.port,
            &self.token,
            path,
            DEFAULT_READ_TIMEOUT,
        )?)
    }

    pub(crate) fn post(
        &self,
        path: &str,
        body: &Value,
        timeout: Duration,
    ) -> Result<Value, String> {
        daemon_http::json_or_error(daemon_http::post_json(
            self.port,
            &self.token,
            path,
            body,
            timeout,
        )?)
    }

    /// The daemon's own report of whether its key is in the development file.
    pub(crate) fn development(&self) -> Result<bool, String> {
        let status = self.get("/api/v1/secrets/presence/status")?;
        Ok(status
            .get("development")
            .and_then(Value::as_bool)
            .unwrap_or(true))
    }

    /// Ask for a nonce and sign `(op, target, nonce)`. The key is read here,
    /// after the presence check, and dropped before this returns.
    pub(crate) fn grant(&self, op: GrantOp, target: &str) -> Result<(String, String), String> {
        let challenge = self.post(
            "/api/v1/secrets/presence/challenge",
            &json!({"op": op.as_str(), "target": target}),
            DEFAULT_READ_TIMEOUT,
        )?;
        let nonce = challenge_nonce(&challenge, op, target)?;
        let key = master_key::read()?;
        let signature = presence_grant::sign(&key, op, target, &nonce);
        drop(key);
        Ok((nonce, signature))
    }
}

/// The nonce from a challenge — but only if the daemon echoed back the very
/// operation and target the person approved. A challenge for anything else is
/// refused rather than signed.
fn challenge_nonce(challenge: &Value, op: GrantOp, target: &str) -> Result<String, String> {
    let echoed_op = challenge.get("op").and_then(Value::as_str);
    let echoed_target = challenge.get("target").and_then(Value::as_str);
    if echoed_op != Some(op.as_str()) || echoed_target != Some(target) {
        return Err("the daemon issued a challenge for a different operation".to_owned());
    }
    challenge
        .get("nonce")
        .and_then(Value::as_str)
        .filter(|n| !n.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| "the daemon's challenge carried no nonce".to_owned())
}

/// The folder from a pick-folder answer: `cancelled` when the person closed
/// the dialog, an explanation when the daemon cannot show one.
fn picked_folder(answer: &Value) -> Result<String, String> {
    if answer.get("available").and_then(Value::as_bool) != Some(true) {
        return Err("a folder picker is not available on this machine".to_owned());
    }
    match answer.get("path").and_then(Value::as_str) {
        Some(path) if !path.is_empty() => Ok(path.to_owned()),
        _ => Err("cancelled".to_owned()),
    }
}

/// An approval id as one path segment. Ids are hex from the daemon; anything
/// that could step outside `/approvals/{id}` is refused rather than escaped.
fn path_segment(id: &str) -> Result<&str, String> {
    if !id.is_empty()
        && id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        Ok(id)
    } else {
        Err(format!("not an approval id: {id:?}"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_challenge_is_signed_only_for_the_operation_the_person_approved() {
        let good =
            json!({"nonce": "n1", "op": "reveal", "target": "gh/token", "expires_in_seconds": 120});
        assert_eq!(
            challenge_nonce(&good, GrantOp::Reveal, "gh/token").unwrap(),
            "n1"
        );
        assert!(challenge_nonce(&good, GrantOp::Reveal, "gh/other").is_err());
        assert!(challenge_nonce(&good, GrantOp::Approve, "gh/token").is_err());
        let no_nonce = json!({"op": "reveal", "target": "gh/token"});
        assert!(challenge_nonce(&no_nonce, GrantOp::Reveal, "gh/token").is_err());
    }

    #[test]
    fn a_closed_picker_is_cancelled_and_a_missing_one_says_so() {
        let picked = json!({"available": true, "path": "/Users/me/Backups"});
        assert_eq!(picked_folder(&picked).unwrap(), "/Users/me/Backups");
        let closed = json!({"available": true, "path": null});
        assert_eq!(picked_folder(&closed).unwrap_err(), "cancelled");
        let headless = json!({"available": false, "path": null});
        assert_ne!(picked_folder(&headless).unwrap_err(), "cancelled");
    }

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

    #[test]
    fn an_approval_id_cannot_leave_its_path_segment() {
        assert_eq!(
            path_segment("0123456789abcdef").unwrap(),
            "0123456789abcdef"
        );
        for bad in ["", "../presence/reveal", "a/b", "a?b", "a b"] {
            assert!(path_segment(bad).is_err(), "{bad}");
        }
    }
}
