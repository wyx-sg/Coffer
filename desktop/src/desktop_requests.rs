//! Serve the command line's desktop requests (spec desktop-app "Serve the
//! command line's desktop requests"; design D8 of
//! `align-cli-with-ui-and-add-tool-environments`).
//!
//! `coffer approval approve <id>` cannot approve anything: it leaves a request
//! with the daemon. Every second this watcher asks the daemon for the next one
//! (the ask is also how the daemon knows the app is running), and runs the
//! SAME presence-checked flow the page's buttons run (`presence_flows.rs`):
//! the approvals are read from the daemon, the operating system's prompt names
//! each one, and the grant is pinned to the target the request was made for.
//! The request's own report — done, cancelled, failed — approves nothing; the
//! command reads the approvals' state from the daemon afterwards.
//!
//! A revealed value is shown in the window and goes nowhere else; a key backup
//! opens the page's own dialog, where the person types the passphrase. A
//! backup request stays open while that dialog is: it ends `done` only when the
//! shell's own export has written the file — with the path and fingerprint the
//! daemon answered, never anything the page says — and `cancelled` when the
//! dialog closes without one (`master_key_backup_closed`), so the command
//! reports what really happened (spec secret "Approve from the command line
//! with the person's own presence check").

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Duration;

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

use crate::daemon_attest;
use crate::daemon_client::Daemon;
use crate::daemon_http::{self, DEFAULT_READ_TIMEOUT};
use crate::discovery::read_daemon_info;
use crate::presence_flows::{self, is_batchable};
use crate::tray_nav;
use crate::updater;

/// How often the daemon is asked for work: a person is waiting on the other end.
const TICK: Duration = Duration::from_secs(1);
/// The event the page shows a revealed value on.
pub const REVEALED_EVENT: &str = "coffer://revealed";
/// The page that holds the master key backup dialog.
const BACKUP_PAGE: &str = "/settings/security?backup=1";
/// The page that holds the master key import dialog.
const IMPORT_PAGE: &str = "/settings/security?import=1";

/// Where `coffer uninstall` opens the confirmation; with `--delete-data` the
/// box starts ticked. The person confirms there, never the command line.
fn uninstall_page(delete_data: bool) -> &'static str {
    if delete_data {
        "/settings/about?uninstall=1&delete=1"
    } else {
        "/settings/about?uninstall=1"
    }
}

/// The backup request waiting on the dialog, if one is: its id. One at a time,
/// because the daemon hands out nothing new while a request is claimed.
static WAITING_BACKUP: Mutex<Option<String>> = Mutex::new(None);

/// How a request ended, as the daemon is told.
#[derive(Debug, PartialEq, Eq)]
pub struct Ending {
    pub status: &'static str,
    pub message: Option<String>,
    pub result: Option<Value>,
}

impl Ending {
    fn done(message: Option<String>, result: Option<Value>) -> Ending {
        Ending {
            status: "done",
            message,
            result,
        }
    }
}

/// A flow's error as an ending: the person declining is `cancelled`, the rest
/// `failed`, with the reason the shell would show.
pub fn ending_of(error: &str) -> Ending {
    let status = if error == "cancelled" {
        "cancelled"
    } else {
        "failed"
    };
    Ending {
        status,
        message: Some(error.to_owned()),
        result: None,
    }
}

/// Start serving. Runs forever on its own thread.
pub fn start(app: AppHandle) {
    std::thread::spawn(move || loop {
        if let Some((port, token)) = read_daemon_info() {
            if let Some(request) = claim(port, &token) {
                // A request is acted on only when the daemon that handed it out
                // proves it is Coffer's: `daemon.json` is writable by any process
                // of this user (spec desktop-app, see `daemon_attest`).
                let ending = match daemon_attest::verify_daemon(port, &token) {
                    Ok(()) => handle(&app, &request),
                    Err(e) => Some(ending_of(&e)),
                };
                // `None`: the request stays open until the dialog it opened ends it.
                if let Some(ending) = ending {
                    finish(port, &token, &request, &ending);
                }
            }
        }
        std::thread::sleep(TICK);
    });
}

fn claim(port: u16, token: &str) -> Option<Value> {
    let response = daemon_http::post_json(
        port,
        token,
        "/api/v1/desktop/requests/claim",
        &json!({}),
        DEFAULT_READ_TIMEOUT,
    )
    .ok()?;
    if response.status != 200 {
        return None;
    }
    serde_json::from_str(&response.body).ok()
}

fn finish(port: u16, token: &str, request: &Value, ending: &Ending) {
    let Some(id) = request.get("id").and_then(Value::as_str) else {
        return;
    };
    finish_id(port, token, id, ending);
}

fn finish_id(port: u16, token: &str, id: &str, ending: &Ending) {
    log::info!("desktop.request id={id} ended {}", ending.status);
    let _ = daemon_http::post_json(
        port,
        token,
        &format!("/api/v1/desktop/requests/{id}/finish"),
        &json!({"status": ending.status, "message": ending.message, "result": ending.result}),
        DEFAULT_READ_TIMEOUT,
    );
}

/// The approvals a request names, each with the target it was asked for.
pub fn pins_of(request: &Value) -> Vec<(String, String)> {
    request
        .get("approvals")
        .and_then(Value::as_array)
        .map(|list| {
            list.iter()
                .filter_map(|a| {
                    Some((
                        a.get("id")?.as_str()?.to_owned(),
                        a.get("fingerprint")?.as_str()?.to_owned(),
                    ))
                })
                .collect()
        })
        .unwrap_or_default()
}

/// Hold a backup request open until the dialog it opens ends it. A request
/// still held from before (none should be) is ended first, as cancelled.
fn hold_backup(id: Option<&str>) {
    let previous = {
        let mut waiting = WAITING_BACKUP.lock().unwrap_or_else(|e| e.into_inner());
        std::mem::replace(&mut *waiting, id.map(str::to_owned))
    };
    if let Some(previous) = previous {
        end_backup_request(&previous, &backup_closed());
    }
}

/// The held backup request, released: the caller ends it.
fn take_backup() -> Option<String> {
    WAITING_BACKUP
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .take()
}

fn end_backup_request(id: &str, ending: &Ending) {
    if let Some((port, token)) = read_daemon_info() {
        finish_id(port, &token, id, ending);
    }
}

/// How a backup request ends when the shell's export wrote the file: the path
/// and fingerprint come from the daemon's answer to the export, not the page.
pub fn backup_written(path: &str, fingerprint: &str) -> Ending {
    Ending::done(
        Some(format!("the backup was written to {path}")),
        Some(json!({"path": path, "fingerprint": fingerprint})),
    )
}

/// How a backup request ends when its dialog closes with no file written.
pub fn backup_closed() -> Ending {
    Ending {
        status: "cancelled",
        message: Some("the backup dialog was closed without writing a backup".into()),
        result: None,
    }
}

/// The shell's export wrote a backup: end the request waiting on it, if any.
pub fn report_backup_written(path: &str, fingerprint: &str) {
    if let Some(id) = take_backup() {
        end_backup_request(&id, &backup_written(path, fingerprint));
    }
}

/// The page's backup dialog closed. A request still waiting on it gets no
/// backup: it ends cancelled. After a written backup there is none left.
#[tauri::command]
pub fn master_key_backup_closed() {
    if let Some(id) = take_backup() {
        end_backup_request(&id, &backup_closed());
    }
}

fn handle(app: &AppHandle, request: &Value) -> Option<Ending> {
    let op = request
        .get("op")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if op == "export_master_key" {
        hold_backup(request.get("id").and_then(Value::as_str));
        tray_nav::open_page(app, BACKUP_PAGE);
        return None;
    }
    Some(match op {
        "approve" => approve(app, &pins_of(request)),
        "reveal" => reveal(
            app,
            request
                .get("ref")
                .and_then(Value::as_str)
                .unwrap_or_default(),
        ),
        "import_master_key" => {
            tray_nav::open_page(app, IMPORT_PAGE);
            Ending::done(
                Some("opened the master key import in the Coffer app".into()),
                None,
            )
        }
        "uninstall" => {
            let delete_data = request
                .get("enabled")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            tray_nav::open_page(app, uninstall_page(delete_data));
            Ending::done(
                Some("opened Uninstall Coffer in the Coffer app".into()),
                None,
            )
        }
        "update_status" => Ending::done(None, serde_json::to_value(updater::status(app)).ok()),
        "update_check" => match tauri::async_runtime::block_on(updater::run_check(app)) {
            Ok(status) => Ending::done(None, serde_json::to_value(status).ok()),
            Err(e) => ending_of(&e),
        },
        "update_install" => match tauri::async_runtime::block_on(updater::run_install(app)) {
            Ok(()) => Ending::done(Some("installed; the app restarts".into()), None),
            Err(e) => ending_of(&e),
        },
        "update_auto_check" => {
            let enabled = request
                .get("enabled")
                .and_then(Value::as_bool)
                .unwrap_or(true);
            let status = updater::set_update_auto_check(app.clone(), enabled);
            Ending::done(None, serde_json::to_value(status).ok())
        }
        other => ending_of(&format!("this app does not know the request {other:?}")),
    })
}

fn approve(app: &AppHandle, pins: &[(String, String)]) -> Ending {
    let run = || -> Result<(), String> {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        let expected: HashMap<String, String> = pins.iter().cloned().collect();
        // Each approval that may not be one of several gets its own prompt.
        let mut batch: Vec<String> = Vec::new();
        for (id, pin) in pins {
            let approval = daemon.get(&format!(
                "/api/v1/secrets/approvals/{}",
                crate::daemon_client::path_segment(id)?
            ))?;
            if pins.len() > 1 && is_batchable(&approval) {
                batch.push(id.clone());
            } else {
                presence_flows::approve_one(app, &daemon, development, id, Some(pin))?;
            }
        }
        if !batch.is_empty() {
            presence_flows::approve_batch(app, &daemon, development, &batch, Some(&expected))?;
        }
        Ok(())
    };
    match run() {
        Ok(()) => Ending::done(None, None),
        Err(e) => ending_of(&e),
    }
}

fn reveal(app: &AppHandle, secret_ref: &str) -> Ending {
    let run = || -> Result<(), String> {
        let daemon = Daemon::find()?;
        let development = daemon.development()?;
        let value = presence_flows::reveal(app, &daemon, development, secret_ref)?;
        // Shown in the window, and nowhere else: not the daemon, not the log.
        tray_nav::show_window(app);
        app.emit_to(
            "main",
            REVEALED_EVENT,
            json!({"ref": secret_ref, "value": value}),
        )
        .map_err(|e| format!("the window could not show it: {e}"))
    };
    match run() {
        Ok(()) => Ending::done(Some("shown in the Coffer app".into()), None),
        Err(e) => ending_of(&e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // acceptance(spec = "desktop-app", scenario = "the shell serves a command line approval")
    #[test]
    fn a_request_names_its_approvals_with_their_targets() {
        let request = json!({"id": "r1", "op": "approve", "approvals": [
            {"id": "a1", "fingerprint": "fp1"},
            {"id": "a2", "fingerprint": "fp2"},
            {"fingerprint": "no id"}
        ]});
        assert_eq!(
            pins_of(&request),
            vec![("a1".into(), "fp1".into()), ("a2".into(), "fp2".into())]
        );
        assert!(pins_of(&json!({"op": "approve"})).is_empty());
    }

    // acceptance(spec = "secret", scenario = "a key backup started from the command line reports what was written")
    #[test]
    fn a_backup_request_ends_with_the_written_file_or_as_cancelled() {
        let written = backup_written("/tmp/qa-cli/coffer-master-key.cfk", "ab12");
        assert_eq!(written.status, "done");
        assert_eq!(
            written.result,
            Some(json!({"path": "/tmp/qa-cli/coffer-master-key.cfk", "fingerprint": "ab12"}))
        );
        let closed = backup_closed();
        assert_eq!(closed.status, "cancelled");
        assert!(closed.result.is_none());
    }

    #[test]
    fn a_held_backup_request_is_taken_once() {
        // No daemon.json in a test: ending a request is a no-op, holding is not.
        *WAITING_BACKUP.lock().unwrap() = Some("r1".into());
        assert_eq!(take_backup().as_deref(), Some("r1"));
        assert_eq!(take_backup(), None);
    }

    // acceptance(spec = "desktop-app", scenario = "the shell opens the uninstall dialog for the command line")
    #[test]
    fn coffer_uninstall_opens_the_dialog_and_removes_nothing() {
        assert_eq!(uninstall_page(false), "/settings/about?uninstall=1");
        assert_eq!(uninstall_page(true), "/settings/about?uninstall=1&delete=1");
    }

    #[test]
    fn a_declined_check_is_cancelled_and_anything_else_failed() {
        assert_eq!(ending_of("cancelled").status, "cancelled");
        let failed = ending_of("the presence check failed: x");
        assert_eq!(failed.status, "failed");
        assert_eq!(
            failed.message.as_deref(),
            Some("the presence check failed: x")
        );
    }
}
