// Tauri 2 entry point. The `mobile_entry_point` macro lets the same crate
// be reused later for iOS/Android without restructuring.
//
// The shell owns exactly what a browser cannot do for itself — a window with
// a Dock icon, a resident tray, detect-or-spawn of the daemon, and the
// credential handshake a locally-hosted page cannot get any other way (see
// docs/decisions/desktop-shell-over-a-shared-frontend.md). Everything else,
// including native file actions, goes through the daemon's HTTP routes in
// both hosts.
//
// The logic lives in sibling modules to keep every file under the project's
// 400-line size cap (see `.agents/stack.md`):
//   * `logging`   — where the shell's own log records go
//   * `sidecar`   — find a binary Tauri staged in the app bundle
//   * `resolve`   — the five-step "where does a daemon come from" chain
//   * `discovery` — ~/.coffer/daemon.json + liveness/shutdown probes
//   * `env_path`  — the $PATH a spawned daemon is handed
//   * `spawn`     — start a daemon detached from the app
//   * `restart`   — the pure restart policy: rate limit, stop-then-start
//   * `daemon`    — the IPC commands and the detect-or-spawn policy
//   * `tray`      — system tray icon + close-to-tray logic

mod daemon;
mod discovery;
mod env_path;
mod logging;
mod resolve;
mod restart;
mod sidecar;
mod spawn;
mod sync_alert;
mod sync_watch;
mod tray;

use tauri::{RunEvent, WindowEvent};
// `Manager` (for `get_webview_window`) is only used by the macOS-only Reopen
// handler below; gate the import so non-macOS builds don't warn on it.
#[cfg(target_os = "macos")]
use tauri::Manager;

use tray::should_close_app;

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // First, before anything that might want to report a failure: install the
    // logger. The `log` facade drops every record until one is set, and the
    // records this crate writes — which binary the resolution chain picked, a
    // restart asked from the tray that failed — are a user's only account of a
    // daemon that never came up. See `logging.rs` for the file they go to.
    logging::install();

    // No `dialog` / `opener` plugins: the frontend reaches OS file actions
    // through daemon HTTP routes in both hosts, so registering them here would
    // only widen the capability set for code nothing calls. `notification` IS
    // registered, and `Cargo.toml` says why that is the same test rather than
    // an exception to it: no daemon route can raise a macOS notification as
    // Coffer, and nothing in the frontend calls this one — it is Rust-side
    // only, for a vault held where nobody is looking (spec vault-sync FR-096).
    //
    // No binary deployment either. The daemon's own frozen-start path
    // (spec daemon FR-027) deploys `coffer`, `coffer-daemon`,
    // `coffer-mcp-shim` and `coffer-callback` into ~/.coffer/bin — which is
    // also how installing only the .app installs the CLI. Doing it here as
    // well would put two processes in a race to write that directory.
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            daemon::restart_daemon,
            daemon::get_daemon_info,
            daemon::daemon_version_matches,
        ])
        .setup(|app| {
            let sync_item = tray::build_tray(app.handle())?;
            // The watcher renames that entry, badges the tray and the Dock, and
            // raises one notification per transition into an attention state.
            sync_watch::start(app.handle().clone(), sync_item);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Intercept close — hide to tray instead of exiting.
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        // `_app` is referenced only by the macOS-gated Reopen arm; the
        // underscore keeps non-macOS builds (where that arm is cfg'd out)
        // from warning about an unused binding.
        .run(|_app, event| match event {
            // Don't quit when the last window is closed — the app lives in
            // the tray. Explicit `app.exit(0)` (Quit menu) carries code=Some(0).
            RunEvent::ExitRequested { api, code, .. } if !should_close_app(code) => {
                api.prevent_exit();
            }
            // macOS sends Reopen when the user clicks the Dock icon for an
            // already-running app. Because CloseRequested hides the window
            // (close-to-tray) instead of destroying it, the window is merely
            // hidden — re-show + focus it so the Dock icon brings Coffer back.
            // Without this the app appears "dead" after closing: still running
            // in the tray, but clicking the Dock icon does nothing.
            // `RunEvent::Reopen` only exists on macOS.
            #[cfg(target_os = "macos")]
            RunEvent::Reopen { .. } => {
                if let Some(window) = _app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                    let _ = window.unminimize();
                }
            }
            _ => {}
        });
}
