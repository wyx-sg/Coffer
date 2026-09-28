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

use std::sync::Mutex;

use crate::sync_presentation::tray_label;
use crate::sync_watch::SYNC_MENU_ITEM_ID;
use crate::tray_locale::{self, tray_text, Lang};

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

/// Where the Sync entry sits in the menu when it is shown: right after "Open
/// Coffer".
pub const SYNC_MENU_POSITION: usize = 1;

/// The tray's menu and its Sync entry, which `lib.rs` hands to the watcher.
pub struct TrayMenu {
    pub menu: Menu<Wry>,
    pub sync: MenuItem<Wry>,
}

/// Build the tray. Returns the menu and the sync entry, which `lib.rs` hands to
/// the watcher — the watcher renames the entry as the vault's state changes
/// (spec vault-sync "Say a vault needs a human where the user already is"), and
/// puts it into or takes it out of the menu as the `vault_sync` experimental
/// feature switches (spec experimental-features "Withdraw what a switched-off
/// feature put in front of agents"), so the two have to be introduced somewhere and the
/// composition root is the honest place.
pub fn build_tray(app: &AppHandle) -> tauri::Result<TrayMenu> {
    // Labelled in the language the tray knows at launch — the OS language,
    // until the page says which one the user chose (`set_ui_language`).
    let text = tray_text(tray_locale::current());
    let open = MenuItem::with_id(app, "open", text.open, true, None::<&str>)?;
    // A route to the `/sync` page. Its label is where a held, conflicted or
    // unpushed vault says so in the one place a user who has closed the window
    // still looks. It starts OUT of the menu: the watcher inserts it at
    // `SYNC_MENU_POSITION` once the daemon reports `vault_sync` on, so a build
    // whose feature is off never shows it, not even for the first tick.
    let sync = MenuItem::with_id(app, SYNC_MENU_ITEM_ID, text.sync_idle, true, None::<&str>)?;
    // The tray must offer "Restart daemon" (spec desktop-app "Find or start a
    // daemon by a fixed resolution order"). It is one
    // of the two places that action lives; the other is the offline banner.
    let restart = MenuItem::with_id(app, "restart_daemon", text.restart, true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", text.quit, true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&open, &restart, &sep, &quit])?;
    app.manage(TrayItems {
        open,
        restart,
        quit,
        sync: sync.clone(),
        attention: Mutex::new(None),
    });

    let icon = base_tray_icon(app);

    let _tray = TrayIconBuilder::with_id(TRAY_ID)
        .menu(&menu)
        .show_menu_on_left_click(true)
        .icon(icon)
        .tooltip(text.tooltip)
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
    Ok(TrayMenu { menu, sync })
}

/// Every labelled thing in the tray, kept so a language switch can relabel
/// them, plus the sync condition the Sync entry is currently naming (`None`
/// when idle) — the one label that depends on more than the language.
pub struct TrayItems {
    open: MenuItem<Wry>,
    restart: MenuItem<Wry>,
    quit: MenuItem<Wry>,
    sync: MenuItem<Wry>,
    attention: Mutex<Option<String>>,
}

/// Record the sync condition the Sync entry names (`None` for idle) and
/// relabel. `sync_watch.rs` calls this whenever an alert is raised or cleared.
pub fn set_sync_attention(app: &AppHandle, status: Option<&str>) {
    if let Some(items) = app.try_state::<TrayItems>() {
        *items.attention.lock().unwrap_or_else(|e| e.into_inner()) = status.map(str::to_owned);
    }
    relabel(app);
}

/// Write every tray label, and the tooltip, in the current language. Menu
/// calls from off the main thread are dispatched to it by Tauri's wrappers;
/// a failed one is dropped — a stale label is not worth a panicked thread.
pub fn relabel(app: &AppHandle) {
    let Some(items) = app.try_state::<TrayItems>() else {
        return;
    };
    let lang = tray_locale::current();
    let text = tray_text(lang);
    let attention = items
        .attention
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone();
    let _ = items.open.set_text(text.open);
    let _ = items.restart.set_text(text.restart);
    let _ = items.quit.set_text(text.quit);
    let _ = items.sync.set_text(match attention.as_deref() {
        Some(status) => tray_label(status, lang),
        None => text.sync_idle.to_owned(),
    });
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let tooltip = if attention.is_some() {
            text.tooltip_attention
        } else {
            text.tooltip
        };
        let _ = tray.set_tooltip(Some(tooltip));
    }
}

/// The page tells the shell its interface language — once when it starts,
/// and again on every switch — and the tray relabels at once (spec
/// desktop-app "Host the UI locally in an application window"). `async` so
/// it runs off the main thread, which the menu wrappers dispatch back to.
#[tauri::command(async)]
pub fn set_ui_language(app: AppHandle, language: String) {
    if tray_locale::choose(Lang::from_tag(&language)) {
        log::info!("tray.language {language}");
        relabel(&app);
    }
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
