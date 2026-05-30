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
        ])
        .setup(|app| {
            tray::build_tray(&app.handle())?;

            // Auto-deploy the bundled shim binary to the user's PATH on every
            // startup. Idempotent (skips when fresh per shim_needs_copy).
            // Best-effort — log and continue on failure; users can fall back
            // to the manual "Deploy shim" button in Daemon settings.
            // `deploy_shim_to_user_path` does synchronous blocking fs work
            // (metadata/read/copy), so run it on a blocking thread rather than
            // an async worker to keep the tokio runtime responsive.
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn_blocking(move || {
                match shim::deploy_shim_to_user_path(app_handle) {
                    Ok(result) => {
                        if result.deployed {
                            log::info!("shim auto-deployed to {}", result.path);
                        } else {
                            log::debug!("shim already current at {}", result.path);
                        }
                    }
                    Err(e) => {
                        log::warn!("shim auto-deploy failed: {}", e);
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
        .run(|_app, event| {
            // Don't quit when the last window is closed — the app lives in
            // the tray. Explicit `app.exit(0)` (Quit menu) carries code=Some(0).
            if let RunEvent::ExitRequested { api, code, .. } = event {
                if !should_close_app(code) {
                    api.prevent_exit();
                }
            }
        });
}
