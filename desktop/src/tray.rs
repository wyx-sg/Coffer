//! Tray icon + close-to-tray logic.
//!
//! Split out of `lib.rs` to keep the top-level entry-point file under the
//! project's 400-line cap (see `.agents/stack.md`).

use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    AppHandle, Manager, Wry,
};

use crate::sync_watch::{SYNC_MENU_IDLE_LABEL, SYNC_MENU_ITEM_ID};

/// The tray's id, so `sync_watch.rs` can find it again to repaint its icon.
pub const TRAY_ID: &str = "coffer-tray";

/// The unmarked tray icon: the app's own window icon, falling back to the
/// bundled PNG. Shared with `sync_watch.rs`, which badges this image rather
/// than shipping a second asset that could drift from it.
pub fn base_tray_icon(app: &AppHandle) -> Image<'static> {
    app.default_window_icon()
        .cloned()
        .map(Image::to_owned)
        .unwrap_or_else(|| {
            Image::from_bytes(include_bytes!("../icons/icon.png"))
                .expect("tray icon bytes valid PNG")
                .to_owned()
        })
}

/// Build the tray. Returns the sync entry, which `lib.rs` hands to the watcher
/// — the watcher renames it as the vault's state changes (spec vault-sync "Say
/// a vault needs a human where the user already is"), so the two have to be introduced somewhere
/// and the composition root is the honest place.
pub fn build_tray(app: &AppHandle) -> tauri::Result<MenuItem<Wry>> {
    let open = MenuItem::with_id(app, "open", "Open Coffer", true, None::<&str>)?;
    // Always present, always a route to the `/sync` page. Its label is where a
    // held, conflicted or unpushed vault says so in the one place a user who
    // has closed the window still looks.
    let sync = MenuItem::with_id(
        app,
        SYNC_MENU_ITEM_ID,
        SYNC_MENU_IDLE_LABEL,
        true,
        None::<&str>,
    )?;
    // The tray must offer "Restart daemon" (spec desktop-app "Find or start a
    // daemon by a fixed resolution order"). It is one
    // of the two places that action lives; the other is the offline banner.
    let restart = MenuItem::with_id(app, "restart_daemon", "Restart daemon", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit Coffer", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&open, &sync, &restart, &sep, &quit])?;

    let icon = base_tray_icon(app);

    let _tray = TrayIconBuilder::with_id(TRAY_ID)
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
                // to show a dialog, so the outcome goes to the log — which
                // `logging.rs` puts in `~/.coffer/logs/daemon.log`, where the
                // CLI's own messages and the Activity page already send a user
                // looking for a daemon that will not start.
                let app = app.clone();
                std::thread::spawn(move || match crate::daemon::restart_daemon(app) {
                    Ok(r) => {
                        log::info!("tray.restart_daemon ok pid={} started={}", r.pid, r.started)
                    }
                    Err(e) => log::warn!("tray.restart_daemon failed: {e}"),
                });
            }
            SYNC_MENU_ITEM_ID => {
                // The click target spec vault-sync "Say a vault needs a human
                // where the user already is" asks for. A desktop notification
                // raised through `tauri-plugin-notification` carries no click
                // handler on macOS, so this entry — whose label is the alert —
                // is what takes the user to the page that can resolve it.
                crate::sync_watch::open_sync_page(app);
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(sync)
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

    /// The load-bearing half of close-to-tray: an exit request carrying no
    /// code is the OS closing the last window, and answering `false` to it is
    /// what makes `lib.rs` call `api.prevent_exit()` — the process stays alive
    /// with its tray entry rather than ending.
    ///
    /// The other two halves of the scenario are Tauri-runtime callbacks with
    /// no pure decision to extract: hiding the window (`api.prevent_close()` +
    /// `window.hide()`) and restoring it on `RunEvent::Reopen` both need a
    /// live window handle. They are exercised by launching the app, not here.
    // acceptance(spec = "desktop-app", scenario = "closing the window hides the app to the tray")
    #[test]
    fn test_should_close_app_returns_false_when_no_code() {
        // OS close / last-window-closed path — stay in tray.
        assert!(!should_close_app(None));
    }

    // acceptance(spec = "desktop-app", scenario = "closing the window hides the app to the tray")
    #[test]
    fn test_should_close_app_returns_true_when_code_present() {
        // Quit menu calls app.exit(0) — actually exit.
        assert!(should_close_app(Some(0)));
        assert!(should_close_app(Some(1)));
    }
}
