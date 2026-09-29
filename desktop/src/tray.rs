//! The menu bar item: its icon, its menu, and close-to-tray.
//!
//! What every label, checkmark, enabled flag and icon should be is decided in
//! `tray_state.rs` from one [`TrayState`]; this module builds the native menu
//! once and writes those answers onto it whenever the state changes. The state
//! is fed by `tray_watch.rs` (the daemon, the attention list, Start at login),
//! `sync_watch.rs` (a raised sync alert), `updater.rs` (the update entry) and
//! the page (`set_ui_language`).

use std::sync::Mutex;

use tauri::{
    image::Image,
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    AppHandle, Manager, Wry,
};

use crate::tray_locale::{self, tray_text, Lang};
use crate::tray_nav::{open_page, open_settings, show_window};
use crate::tray_state::{self as view, Icon, TrayState};
use crate::update_state::UpdateStatus;

/// The tray's id.
pub const TRAY_ID: &str = "coffer-tray";

/// Where the "N things need you" entry sits when it is shown: right under the
/// status line.
const ATTENTION_POSITION: usize = 1;

/// The template images, rendered from `icons/tray/*.svg` by
/// `scripts/render_tray_icons.sh`: black on transparent, which macOS tints for
/// a light or a dark menu bar. `@2x` is drawn on a Retina display.
const ICONS: [(Icon, &[u8], &[u8]); 3] = [
    (
        Icon::Normal,
        include_bytes!("../icons/tray/tray.png"),
        include_bytes!("../icons/tray/tray@2x.png"),
    ),
    (
        Icon::Attention,
        include_bytes!("../icons/tray/tray-attention.png"),
        include_bytes!("../icons/tray/tray-attention@2x.png"),
    ),
    (
        Icon::Offline,
        include_bytes!("../icons/tray/tray-offline.png"),
        include_bytes!("../icons/tray/tray-offline@2x.png"),
    ),
];

fn icon_image(icon: Icon, retina: bool) -> Image<'static> {
    let (_, one, two) = ICONS
        .iter()
        .find(|(i, _, _)| *i == icon)
        .expect("every icon has an image");
    Image::from_bytes(if retina { two } else { one })
        .expect("tray icon bytes are a valid PNG")
        .to_owned()
}

/// Every item the state is written onto, and the state itself.
pub struct TrayItems {
    menu: Menu<Wry>,
    status: MenuItem<Wry>,
    attention: MenuItem<Wry>,
    open: MenuItem<Wry>,
    new_conversation: MenuItem<Wry>,
    settings: MenuItem<Wry>,
    update: MenuItem<Wry>,
    login: CheckMenuItem<Wry>,
    daemon: MenuItem<Wry>,
    quit: MenuItem<Wry>,
    retina: bool,
    state: Mutex<TrayState>,
    attention_shown: Mutex<bool>,
    /// The icon last drawn, so a poll that changes nothing repaints nothing.
    drawn: Mutex<Option<Icon>>,
}

/// Build the menu bar item, in the order of the design canvas (1.5 Menu bar).
pub fn build_tray(app: &AppHandle, update: UpdateStatus) -> tauri::Result<()> {
    let t = tray_text(tray_locale::current());
    let item = |id: &str, label: &str, enabled: bool, accel: Option<&str>| {
        MenuItem::with_id(app, id, label, enabled, accel)
    };
    let status = item("status", t.status_connecting, false, None)?;
    let attention = item("needs_you", t.needs_you_one, true, None)?;
    let open = item("open", t.open, true, None)?;
    let new_conversation = item("new_conversation", t.new_conversation, false, None)?;
    let settings = item("settings", t.settings, false, Some("CmdOrCtrl+,"))?;
    let update_item = item("update", t.check_updates, true, None)?;
    let login = CheckMenuItem::with_id(
        app,
        "start_at_login",
        t.start_at_login,
        false,
        false,
        None::<&str>,
    )?;
    let daemon = item("restart_daemon", t.restart, true, None)?;
    let quit = item("quit", t.quit, true, Some("CmdOrCtrl+Q"))?;
    let sep = || PredefinedMenuItem::separator(app);
    // The attention entry starts out of the menu; `render` inserts it.
    let menu = Menu::with_items(
        app,
        &[
            &status,
            &sep()?,
            &open,
            &new_conversation,
            &settings,
            &sep()?,
            &update_item,
            &login,
            &sep()?,
            &daemon,
            &quit,
        ],
    )?;
    let retina = app
        .primary_monitor()
        .ok()
        .flatten()
        .is_none_or(|m| m.scale_factor() >= 1.5);

    TrayIconBuilder::with_id(TRAY_ID)
        .menu(&menu)
        .show_menu_on_left_click(true)
        .icon(icon_image(Icon::Normal, retina))
        .icon_as_template(true)
        .tooltip(t.tooltip)
        .on_menu_event(|app, event| on_menu(app, event.id.as_ref()))
        .build(app)?;

    app.manage(TrayItems {
        menu,
        status,
        attention,
        open,
        new_conversation,
        settings,
        update: update_item,
        login,
        daemon,
        quit,
        retina,
        state: Mutex::new(TrayState::new(update)),
        attention_shown: Mutex::new(false),
        drawn: Mutex::new(Some(Icon::Normal)),
    });
    render(app);
    Ok(())
}

fn on_menu(app: &AppHandle, id: &str) {
    match id {
        "open" => show_window(app),
        "needs_you" => open_page(app, "/"),
        "new_conversation" => open_page(app, "/conversations"),
        "settings" => open_settings(app, "general"),
        "update" => on_update(app),
        "start_at_login" => crate::tray_watch::toggle_login(app.clone()),
        "restart_daemon" => {
            // The same rate-limited stop-then-spawn the offline banner uses,
            // off the menu thread: a true restart blocks for seconds. The
            // outcome goes to the daemon log (`logging.rs`), the menu bar
            // having no place for a dialog.
            let app = app.clone();
            std::thread::spawn(move || match crate::daemon::restart_daemon(app.clone()) {
                Ok(r) => {
                    log::info!("tray.restart_daemon ok pid={} started={}", r.pid, r.started);
                    crate::tray_watch::refresh(&app);
                }
                Err(e) => log::warn!("tray.restart_daemon failed: {e}"),
            });
        }
        "quit" => app.exit(0),
        _ => {}
    }
}

/// "Restart to install" installs the update on offer — the user's own choice,
/// as Download and restart is on the About tab. "Check for updates…" opens
/// About, where the check's answer is shown, and checks.
fn on_update(app: &AppHandle) {
    let offered = crate::updater::status(app);
    let app = app.clone();
    if offered.available.is_some() && !offered.busy() {
        tauri::async_runtime::spawn(async move {
            let _ = crate::updater::run_install(&app).await;
        });
    } else {
        open_settings(&app, "about");
        tauri::async_runtime::spawn(async move {
            let _ = crate::updater::run_check(&app).await;
        });
    }
}

/// Change the state and redraw.
pub fn update_state(app: &AppHandle, change: impl FnOnce(&mut TrayState)) {
    if let Some(items) = app.try_state::<TrayItems>() {
        change(&mut items.state.lock().unwrap_or_else(|e| e.into_inner()));
    }
    render(app);
}

/// The state as it stands.
pub fn snapshot(app: &AppHandle) -> Option<TrayState> {
    let items = app.try_state::<TrayItems>()?;
    let state = items
        .state
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone();
    Some(state)
}

/// Record the updater's latest record (`updater.rs`).
pub fn set_update(app: &AppHandle, update: UpdateStatus) {
    update_state(app, |s| s.update = update);
}

/// Record the sync condition a raised alert names (`None` when cleared).
pub fn set_sync_alert(app: &AppHandle, status: Option<&str>) {
    update_state(app, |s| s.sync_alert = status.map(str::to_owned));
}

/// Write the state onto the menu and the icon, in the current language. Menu
/// calls from off the main thread are dispatched to it by Tauri's wrappers; a
/// failed one is dropped — a stale label is not worth a panicked thread.
pub fn render(app: &AppHandle) {
    let Some(items) = app.try_state::<TrayItems>() else {
        return;
    };
    let lang = tray_locale::current();
    let state = items
        .state
        .lock()
        .unwrap_or_else(|e| e.into_inner())
        .clone();
    write_menu(&items, &state, lang);
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let icon = view::icon(&state);
        let mut drawn = items.drawn.lock().unwrap_or_else(|e| e.into_inner());
        if *drawn != Some(icon) {
            let _ = tray.set_icon(Some(icon_image(icon, items.retina)));
            let _ = tray.set_icon_as_template(true);
            *drawn = Some(icon);
        }
        let _ = tray.set_tooltip(Some(view::tooltip(&state, lang)));
    }
}

fn write_menu(items: &TrayItems, state: &TrayState, lang: Lang) {
    let t = tray_text(lang);
    let online = view::needs_daemon_enabled(state);
    let _ = items.status.set_text(view::status_line(state, lang));
    let _ = items.open.set_text(t.open);
    let _ = items.new_conversation.set_text(t.new_conversation);
    let _ = items.new_conversation.set_enabled(online);
    let _ = items.settings.set_text(t.settings);
    let _ = items.settings.set_enabled(online);
    let (update_label, update_enabled) = view::update_item(&state.update, lang);
    let _ = items.update.set_text(update_label);
    let _ = items.update.set_enabled(update_enabled);
    let (login_enabled, login_checked) = view::login_item(state);
    let _ = items.login.set_text(t.start_at_login);
    let _ = items.login.set_enabled(login_enabled);
    let _ = items.login.set_checked(login_checked);
    let _ = items.daemon.set_text(view::daemon_action(state, lang));
    let _ = items.quit.set_text(t.quit);

    let mut shown = items
        .attention_shown
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    match view::attention_label(state, lang) {
        Some(label) => {
            let _ = items.attention.set_text(label);
            if !*shown
                && items
                    .menu
                    .insert(&items.attention, ATTENTION_POSITION)
                    .is_ok()
            {
                *shown = true;
            }
        }
        None => {
            if *shown && items.menu.remove(&items.attention).is_ok() {
                *shown = false;
            }
        }
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
        render(&app);
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

    #[test]
    fn every_icon_state_has_a_template_image_at_both_scales() {
        for icon in [Icon::Normal, Icon::Attention, Icon::Offline] {
            for retina in [false, true] {
                let image = icon_image(icon, retina);
                let side = if retina { 36 } else { 18 };
                assert_eq!((image.width(), image.height()), (side, side), "{icon:?}");
                // A template image is alpha only: every pixel is black.
                assert!(image
                    .rgba()
                    .chunks(4)
                    .all(|p| p[3] == 0 || (p[0], p[1], p[2]) == (0, 0, 0)));
            }
        }
    }
}
