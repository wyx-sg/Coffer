//! Tray icon + close-to-tray logic.
//!
//! Split out of `lib.rs` to keep the top-level entry-point file under the
//! project's 400-line cap (see `agents/stack.md`).

use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    AppHandle, Manager,
};

pub fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open Coffer", true, None::<&str>)?;
    // FR-D03: the tray must offer "Restart daemon" (spec 003-mcp-gateway-desktop).
    let restart = MenuItem::with_id(app, "restart_daemon", "Restart daemon", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Coffer", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&open, &restart, &sep, &quit])?;

    let icon = app.default_window_icon().cloned().unwrap_or_else(|| {
        Image::from_bytes(include_bytes!("../icons/icon.png")).expect("tray icon bytes valid PNG")
    });

    let _tray = TrayIconBuilder::with_id("coffer-tray")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .icon(icon)
        .tooltip("Coffer")
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                    let _ = window.unminimize();
                }
            }
            "restart_daemon" => {
                // Same rate-limited stop-then-spawn the webview banner uses
                // (daemon.rs::restart_daemon). Run off the menu-event thread:
                // a true restart blocks for seconds (shutdown + port-free
                // poll), which must not freeze the UI. The tray has no place
                // to show a dialog, so the outcome is just logged.
                let app = app.clone();
                std::thread::spawn(move || match crate::daemon::restart_daemon(app) {
                    Ok(r) => log::info!(
                        "tray.restart_daemon ok pid={} started={}",
                        r.pid,
                        r.started
                    ),
                    Err(e) => log::warn!("tray.restart_daemon failed: {e}"),
                });
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(())
}

/// Return `true` when the close event should actually exit the application.
/// Currently we always hide to the tray; this function exists as the single
/// decision point so unit tests can cover the logic without spinning up a
/// full Tauri runtime.
pub fn should_close_app(code: Option<i32>) -> bool {
    // Only exit when an explicit exit code is provided (e.g. app.exit(0)
    // called from the Quit menu item). A `None` code means the OS closed
    // the last window — we intercept that and stay in the tray instead.
    code.is_some()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_should_close_app_returns_false_when_no_code() {
        // OS close / last-window-closed path — stay in tray.
        assert!(!should_close_app(None));
    }

    #[test]
    fn test_should_close_app_returns_true_when_code_present() {
        // Quit menu calls app.exit(0) — actually exit.
        assert!(should_close_app(Some(0)));
        assert!(should_close_app(Some(1)));
    }
}
