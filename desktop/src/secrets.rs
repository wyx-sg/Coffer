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

use crate::daemon_client::Daemon;
use crate::presence::{self, Subject};
use crate::presence_flows;
use crate::presence_grant::GrantOp;

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
        presence_flows::reveal(&app, &daemon, development, &secret_ref)
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
        let backup = MasterKeyBackup {
            path: field("path")?,
            fingerprint: field("fingerprint")?,
        };
        // A `coffer secret backup-key` waiting on this dialog learns the file
        // was written — from the daemon's answer above, not from the page.
        crate::desktop_requests::report_backup_written(&backup.path, &backup.fingerprint);
        Ok(backup)
    })
    .await
}

/// Approve a pending request (a secret about to go somewhere new). The prompt
/// carries the daemon's own description of the request, so the person reads
/// what is being approved in the operating system's dialog; the grant is pinned
/// to the target that description names.
#[tauri::command]
pub async fn approve_pending(app: AppHandle, approval_id: String) -> Result<Value, String> {
    blocking(move || {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        presence_flows::approve_one(&app, &daemon, development, &approval_id, None)
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
        presence_flows::approve_batch(&app, &daemon, development, &approval_ids, None)
    })
    .await
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_closed_picker_is_cancelled_and_a_missing_one_says_so() {
        let picked = json!({"available": true, "path": "/Users/me/Backups"});
        assert_eq!(picked_folder(&picked).unwrap(), "/Users/me/Backups");
        let closed = json!({"available": true, "path": null});
        assert_eq!(picked_folder(&closed).unwrap_err(), "cancelled");
        let headless = json!({"available": false, "path": null});
        assert_ne!(picked_folder(&headless).unwrap_err(), "cancelled");
    }
}
