//! Uninstall Coffer from the app (spec desktop-app "Uninstall Coffer from the
//! app"; design D3–D5 of `add-self-update-and-uninstall`).
//!
//! The page's dialog asks; this does it, in order:
//!
//! 1. When the person ticked Also delete my data: a presence check whose
//!    prompt says the data will be deleted, then a grant for `uninstall` over
//!    `delete-data`. A cancelled check sends nothing.
//! 2. From here the shell starts no daemon — not the handshake's cold start,
//!    not a restart (`spawn_resolved_daemon` refuses while [`in_progress`]).
//! 3. `POST /api/v1/daemon/uninstall`: the daemon takes back what it wrote
//!    outside `~/.coffer`, answers with the steps, and stops; with the grant it
//!    deletes `~/.coffer` and the master key once it has.
//! 4. The shell waits for the daemon to go, returns the report for the page to
//!    show, and a moment later moves its own `.app` to the Trash and quits.
//!
//! A failure before the daemon answered clears the flag: nothing was removed
//! and the app carries on.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::AppHandle;

use crate::daemon_client::Daemon;
use crate::discovery::read_daemon_info;
use crate::presence::{self, Subject};
use crate::presence_grant::GrantOp;
use crate::secrets::blocking;

/// What a delete-data grant is signed over; the daemon redeems the same.
pub const DELETE_DATA_TARGET: &str = "delete-data";
/// The daemon's own steps: the agents' configs, skill links and a few files.
const UNINSTALL_TIMEOUT: Duration = Duration::from_secs(120);
/// How long the daemon may take to stop after it answered.
const EXIT_WAIT: Duration = Duration::from_secs(20);
/// How long the page shows what was done before the app goes.
const QUIT_DELAY: Duration = Duration::from_secs(4);

static UNINSTALLING: AtomicBool = AtomicBool::new(false);

/// Whether an uninstall is under way: nothing may start a daemon then.
pub fn in_progress() -> bool {
    UNINSTALLING.load(Ordering::SeqCst)
}

#[tauri::command]
pub async fn uninstall_coffer(app: AppHandle, delete_data: bool) -> Result<Value, String> {
    blocking(move || {
        let daemon = Daemon::find()?;
        let mut body = json!({"delete_data": delete_data});
        if delete_data {
            let development = daemon.development()?;
            presence::confirm(&app, &Subject::DeleteData, development)?;
            let (nonce, signature) = daemon.grant(GrantOp::Uninstall, DELETE_DATA_TARGET)?;
            body["nonce"] = json!(nonce);
            body["signature"] = json!(signature);
        }
        UNINSTALLING.store(true, Ordering::SeqCst);
        let report = match daemon.post("/api/v1/daemon/uninstall", &body, UNINSTALL_TIMEOUT) {
            Ok(report) => report,
            Err(e) => {
                UNINSTALLING.store(false, Ordering::SeqCst);
                return Err(e);
            }
        };
        log::info!("uninstall: the daemon answered; waiting for it to stop");
        if !wait_for_exit(EXIT_WAIT) {
            log::warn!("uninstall: the daemon is still running after {EXIT_WAIT:?}");
        }
        let quitting = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(QUIT_DELAY);
            trash_own_bundle();
            quitting.exit(0);
        });
        Ok(report)
    })
    .await
}

fn wait_for_exit(limit: Duration) -> bool {
    let deadline = Instant::now() + limit;
    while Instant::now() < deadline {
        if read_daemon_info().is_none() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

/// The `.app` this process runs from, if it runs from one — a development
/// build run by cargo does not, and nothing is moved then.
pub fn bundle_of(exe: &Path) -> Option<PathBuf> {
    exe.ancestors()
        .find(|p| p.extension().is_some_and(|e| e == "app"))
        .map(Path::to_path_buf)
}

fn trash_own_bundle() {
    let Some(bundle) = std::env::current_exe().ok().and_then(|e| bundle_of(&e)) else {
        log::info!("uninstall: not running from an .app; nothing to move to the Trash");
        return;
    };
    match trash(&bundle) {
        Ok(()) => log::info!("uninstall: moved {} to the Trash", bundle.display()),
        Err(e) => log::warn!(
            "uninstall: could not move {} to the Trash: {e}",
            bundle.display()
        ),
    }
}

#[cfg(target_os = "macos")]
fn trash(path: &Path) -> Result<(), String> {
    use objc2::rc::Retained;
    use objc2::runtime::AnyObject;
    use objc2::{class, msg_send};
    use objc2_foundation::{NSError, NSString};

    let path = NSString::from_str(&path.to_string_lossy());
    // SAFETY: `fileURLWithPath:` and `defaultManager` return autoreleased
    // objects that `msg_send!` retains; `trashItemAtURL:resultingItemURL:error:`
    // takes a nullable out-pointer for the new URL, passed as null.
    unsafe {
        let url: Retained<AnyObject> = msg_send![class!(NSURL), fileURLWithPath: &*path];
        let manager: Retained<AnyObject> = msg_send![class!(NSFileManager), defaultManager];
        let moved: Result<(), Retained<NSError>> = msg_send![
            &*manager,
            trashItemAtURL: &*url,
            resultingItemURL: std::ptr::null_mut::<*mut AnyObject>(),
            error: _
        ];
        moved.map_err(|e| e.localizedDescription().to_string())
    }
}

#[cfg(not(target_os = "macos"))]
fn trash(_path: &Path) -> Result<(), String> {
    Err("moving the app to the Trash is only done on macOS".to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;

    // acceptance(spec = "desktop-app", scenario = "uninstalling from the app removes Coffer and the app")
    #[test]
    fn the_app_moves_its_own_bundle_and_nothing_else() {
        assert_eq!(
            bundle_of(Path::new("/Applications/Coffer.app/Contents/MacOS/Coffer")),
            Some(PathBuf::from("/Applications/Coffer.app"))
        );
        // A development build run from cargo's target folder has no bundle.
        assert_eq!(
            bundle_of(Path::new("/src/desktop/target/debug/coffer-desktop")),
            None
        );
    }

    // acceptance(spec = "desktop-app", scenario = "deleting the data waits for the person's presence")
    #[test]
    fn the_prompt_says_the_data_is_deleted() {
        let reason = presence::reason(&Subject::DeleteData, false);
        assert!(reason.contains("delete"), "{reason}");
        assert!(reason.contains("master key"), "{reason}");
        assert_eq!(GrantOp::Uninstall.as_str(), "uninstall");
    }

    #[test]
    fn nothing_is_uninstalling_until_the_daemon_is_asked() {
        assert!(!in_progress());
    }
}
