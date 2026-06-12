// Tauri 2 entry point. The `mobile_entry_point` macro lets the same crate
// be reused later for iOS/Android without restructuring.
//
// The bulk of the app logic lives in sibling modules to keep this file
// under the project's 400-line size cap (see `agents/stack.md`):
//   * `shim`   — shim-binary deploy to ~/.coffer/bin/
//   * `daemon` — coffer-daemon spawn + detect-or-spawn + rate-limit
//   * `tray`   — system tray icon + close-to-tray logic

mod daemon;
mod shim;
mod tray;

use tauri::{AppHandle, RunEvent, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
// `Manager` (for `get_webview_window`) is only used by the macOS-only Reopen
// handler below; gate the import so non-macOS builds don't warn on it.
#[cfg(target_os = "macos")]
use tauri::Manager;

// Re-export the close-to-tray decision function so existing integration
// tests can keep importing it via the crate root.
pub use tray::should_close_app;

// ---------------------------------------------------------------------------
// Autostart Tauri commands (thin wrappers around the plugin manager).
// ---------------------------------------------------------------------------

#[tauri::command]
fn set_autostart_enabled(app: AppHandle, enabled: bool) -> Result<bool, String> {
    let manager = app.autolaunch();
    if enabled {
        manager.enable().map_err(|e| e.to_string())?;
    } else {
        manager.disable().map_err(|e| e.to_string())?;
    }
    manager.is_enabled().map_err(|e| e.to_string())
}

#[tauri::command]
fn get_autostart_enabled(app: AppHandle) -> Result<bool, String> {
    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .invoke_handler(tauri::generate_handler![
            set_autostart_enabled,
            get_autostart_enabled,
            daemon::restart_daemon,
            daemon::get_daemon_info,
            daemon::get_app_version,
            daemon::daemon_version_matches,
        ])
        .setup(|app| {
            tray::build_tray(&app.handle())?;

            // Auto-deploy the bundled shim + daemon binaries to the user's
            // PATH on every startup. Idempotent (skips when fresh per
            // shim_needs_copy). Co-locating the daemon lets the frozen shim's
            // detect-or-spawn find its sibling after a reboot (ADR-006).
            // Best-effort — log and continue on failure; users can fall back
            // to the manual "Deploy shim" button in Daemon settings.
            // `deploy_sidecars_to_user_path` does synchronous blocking fs work
            // (metadata/read/copy), so run it on a blocking thread rather than
            // an async worker to keep the tokio runtime responsive.
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn_blocking(move || {
                match shim::deploy_sidecars_to_user_path(app_handle) {
                    Ok(results) => {
                        for result in results {
                            if result.deployed {
                                log::info!("sidecar auto-deployed to {}", result.path);
                            } else {
                                log::debug!("sidecar already current at {}", result.path);
                            }
                        }
                    }
                    Err(e) => {
                        log::warn!("sidecar auto-deploy failed: {}", e);
                    }
                }
            });

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
            RunEvent::ExitRequested { api, code, .. } => {
                if !should_close_app(code) {
                    api.prevent_exit();
                }
            }
            // macOS sends Reopen when the user clicks the Dock icon for an
            // already-running app. Because CloseRequested hides the window
            // (close-to-tray) instead of destroying it, the window is merely
            // hidden — re-show + focus it so the Dock icon brings Coffer back.
            // Without this the app appears "dead" after closing: still running
            // in the tray, but clicking the Dock icon does nothing.
            // `RunEvent::Reopen` only exists on macOS (#[cfg(target_os = "macos")]).
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
