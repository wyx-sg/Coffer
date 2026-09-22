//! The slow poll behind spec vault-sync FR-096, and the surfaces it drives.
//!
//! `sync_alert.rs` decides *whether* the vault's last round needs a human and
//! whether the user has already been told; this module asks the daemon, and
//! turns the answer into the three things a browser tab cannot do for itself —
//! a marked tray icon, a badged Dock icon, and one native notification.
//!
//! The poll is deliberately slow. A converge round runs on an interval measured
//! in tens of minutes, and a hold, a conflict or a failed push persists until a
//! person acts, so there is nothing a tighter loop could learn sooner. It also
//! never runs before the daemon is up: `read_daemon_info` + `daemon_responds_ok`
//! are the same two checks `resolve.rs` gates its take-over on, and a tick that
//! cannot reach a daemon leaves every surface exactly as it found it rather than
//! clearing a real alert because the daemon happened to be restarting.

use std::time::Duration;

use tauri::image::Image;
use tauri::menu::MenuItem;
use tauri::{AppHandle, Manager, Wry};
use tauri_plugin_notification::NotificationExt;

use crate::discovery::{daemon_responds_ok, read_daemon_info};
use crate::sync_alert::{next_action, parse_sync_status, AlertAction, SyncSnapshot};
use crate::sync_presentation::{badge_rgba, notification_body, tray_label, NOTIFICATION_TITLE};
use crate::tray::{base_tray_icon, TRAY_ID};

/// The tray entry this module owns: a permanent route to the `/sync` page whose
/// label becomes the alert when a round needs a human. It is the click target
/// FR-096 asks for — a desktop notification raised through this plugin exposes
/// no click handler on macOS, so the thing the user reaches for after reading
/// the notification is the tray, not the banner.
pub const SYNC_MENU_ITEM_ID: &str = "sync_status";
/// What that entry says when there is nothing outstanding. It claims nothing
/// about the vault's state, so an unconfigured machine — where this module does
/// nothing at all — is not shown a reassurance it has not earned.
pub const SYNC_MENU_IDLE_LABEL: &str = "Sync status";

/// Long enough for the launch handshake's detect-or-spawn to have resolved, so
/// the first tick does not race the daemon the app is still starting.
const FIRST_POLL_DELAY: Duration = Duration::from_secs(30);
/// Ten minutes. FR-096's condition changes at most once a converge interval and
/// then waits for a person; polling harder buys nothing and costs a wakeup.
const POLL_INTERVAL: Duration = Duration::from_secs(600);

/// The Dock badge's text. A single character, because macOS draws it in a
/// circle the size of a favicon.
const DOCK_BADGE: &str = "!";

/// Start watching. Runs forever on its own thread; every effect it performs is
/// dispatched to the main thread by Tauri's own menu/tray/window wrappers.
pub fn start(app: AppHandle, item: MenuItem<Wry>) {
    std::thread::spawn(move || {
        // The status the last raised notification was about. `None` means no
        // mark is showing — see `sync_alert::next_action` for the whole rule.
        let mut notified: Option<String> = None;
        std::thread::sleep(FIRST_POLL_DELAY);
        loop {
            if let Some(snapshot) = poll_once() {
                let action = next_action(notified.as_deref(), &snapshot);
                match &action {
                    AlertAction::Raise(status) => notified = Some(status.clone()),
                    AlertAction::Clear => notified = None,
                    AlertAction::Nothing => {}
                }
                apply(&app, &item, &action);
            }
            std::thread::sleep(POLL_INTERVAL);
        }
    });
}

/// Bring the window up on the sync page. Wired to the tray entry.
pub fn open_sync_page(app: &AppHandle) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let _ = window.show();
    let _ = window.set_focus();
    let _ = window.unminimize();
    let _ = window.eval(NAVIGATE_TO_SYNC_JS);
}

/// The frontend is one `createBrowserRouter` over `frontend/dist` (spec
/// desktop-app FR-002), so the shell navigates it the way the browser host's
/// back button does — push the entry, then let the router's own `popstate`
/// listener read it — rather than gaining a second code path in the page. The
/// existing history state is carried over because React Router keys its listener
/// on the `idx` it keeps there; dropping it would make the event a no-op.
const NAVIGATE_TO_SYNC_JS: &str = "(function(){var s=window.history.state||{idx:0};\
     window.history.pushState(s,'','/sync');\
     window.dispatchEvent(new PopStateEvent('popstate',{state:s}));})()";

/// One tick: is a daemon up, and what does it say. `None` for "could not ask",
/// which is never an answer about the vault.
fn poll_once() -> Option<SyncSnapshot> {
    let (port, token) = read_daemon_info()?;
    if !daemon_responds_ok(port) {
        return None;
    }
    let body = fetch_sync_status(port, &token)?;
    parse_sync_status(&body)
}

/// `GET /api/v1/sync/status`, token-gated like every route but the daemon's own
/// status probe. Raw HTTP/1.1 over `TcpStream`, for the reason `discovery.rs`
/// gives: an HTTP-client dependency is not worth one loopback request.
fn fetch_sync_status(port: u16, token: &str) -> Option<String> {
    use std::io::{Read, Write};
    use std::net::{Ipv4Addr, SocketAddrV4, TcpStream};

    let addr = SocketAddrV4::new(Ipv4Addr::LOCALHOST, port);
    let mut stream = TcpStream::connect_timeout(&addr.into(), Duration::from_millis(500)).ok()?;
    stream
        .set_write_timeout(Some(Duration::from_secs(2)))
        .ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(5))).ok()?;
    let req = format!(
        "GET /api/v1/sync/status HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\
         X-Coffer-Token: {token}\r\nAccept: application/json\r\n\
         Connection: close\r\n\r\n"
    );
    stream.write_all(req.as_bytes()).ok()?;
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).ok()?;
    http_json_body(&String::from_utf8_lossy(&raw))
}

/// The body of a `200` response, or `None` for anything else — a `401` from a
/// rotated token and a `404` from an older daemon both mean "no answer", never
/// "the vault is fine".
fn http_json_body(response: &str) -> Option<String> {
    let (head, body) = response.split_once("\r\n\r\n")?;
    let mut lines = head.lines();
    let status_line = lines.next()?;
    if !status_line.starts_with("HTTP/1.1 200") && !status_line.starts_with("HTTP/1.0 200") {
        return None;
    }
    let chunked = lines.any(|line| {
        let line = line.to_ascii_lowercase();
        line.starts_with("transfer-encoding:") && line.contains("chunked")
    });
    if chunked {
        dechunk(body)
    } else {
        Some(body.to_owned())
    }
}

/// Reassemble a `Transfer-Encoding: chunked` body. The daemon sends a
/// `Content-Length` today; this is here so a server change that switches to
/// chunking degrades to a parse failure a tick later rather than to a feature
/// that silently stopped reporting anything.
fn dechunk(body: &str) -> Option<String> {
    let mut out = String::new();
    let mut rest = body;
    loop {
        let (size_line, tail) = rest.split_once("\r\n")?;
        let size = usize::from_str_radix(size_line.split(';').next()?.trim(), 16).ok()?;
        if size == 0 {
            return Some(out);
        }
        // `get` rather than an index: a chunk boundary that falls inside a
        // multi-byte character would panic on a slice.
        out.push_str(tail.get(..size)?);
        rest = tail.get(size + 2..)?;
    }
}

/// Perform one decision. Every failure here is logged and swallowed: a tray
/// that could not be repainted must not take the poll thread down with it.
fn apply(app: &AppHandle, item: &MenuItem<Wry>, action: &AlertAction) {
    match action {
        AlertAction::Raise(status) => {
            log::warn!("sync.attention raised status={status}");
            mark_icon(app, true);
            let _ = item.set_text(tray_label(status));
            set_dock_badge(app, Some(DOCK_BADGE));
            if let Err(e) = app
                .notification()
                .builder()
                .title(NOTIFICATION_TITLE)
                .body(notification_body(status))
                .show()
            {
                log::warn!("sync.attention notification failed: {e}");
            }
        }
        AlertAction::Clear => {
            log::info!("sync.attention cleared");
            mark_icon(app, false);
            let _ = item.set_text(SYNC_MENU_IDLE_LABEL);
            set_dock_badge(app, None);
        }
        AlertAction::Nothing => {}
    }
}

/// Paint (or un-paint) the alert dot on the tray icon.
fn mark_icon(app: &AppHandle, marked: bool) {
    let Some(tray) = app.tray_by_id(TRAY_ID) else {
        return;
    };
    let base = base_tray_icon(app);
    let (width, height) = (base.width(), base.height());
    let icon = if marked {
        Image::new_owned(badge_rgba(base.rgba(), width, height), width, height)
    } else {
        base
    };
    if let Err(e) = tray.set_icon(Some(icon)) {
        log::warn!("sync.attention tray icon: {e}");
    }
    let tooltip = if marked {
        "Coffer — sync needs attention"
    } else {
        "Coffer"
    };
    let _ = tray.set_tooltip(Some(tooltip));
}

/// The Dock badge. macOS is the only platform the shell ships on (spec
/// desktop-app FR-013) and the only one where Tauri exposes this at all, so the
/// other builds — the Linux `cargo check` CI leg among them — get a no-op.
#[cfg(target_os = "macos")]
fn set_dock_badge(app: &AppHandle, label: Option<&str>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_badge_label(label.map(str::to_owned));
    }
}

#[cfg(not(target_os = "macos"))]
fn set_dock_badge(_app: &AppHandle, _label: Option<&str>) {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn http_json_body_reads_a_content_length_response() {
        let raw = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\
                   Content-Length: 21\r\n\r\n{\"configured\": false}";
        assert_eq!(
            http_json_body(raw).as_deref(),
            Some("{\"configured\": false}")
        );
    }

    #[test]
    fn http_json_body_rejects_a_non_200() {
        // A rotated token gives 401, an older daemon 404. Neither is news
        // about the vault, and treating either as one would clear a real mark.
        for head in ["HTTP/1.1 401 Unauthorized", "HTTP/1.1 404 Not Found"] {
            let raw = format!("{head}\r\nContent-Length: 2\r\n\r\n{{}}");
            assert_eq!(http_json_body(&raw), None);
        }
    }

    #[test]
    fn http_json_body_rejects_a_response_with_no_header_terminator() {
        assert_eq!(http_json_body("HTTP/1.1 200 OK\r\n"), None);
        assert_eq!(http_json_body(""), None);
    }

    #[test]
    fn http_json_body_reassembles_a_chunked_response() {
        let raw = "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n\
                   c\r\n{\"configured\r\n9\r\n\": false}\r\n0\r\n\r\n";
        assert_eq!(
            http_json_body(raw).as_deref(),
            Some("{\"configured\": false}")
        );
    }

    #[test]
    fn dechunk_gives_up_on_a_truncated_body_instead_of_panicking() {
        // Length says 20 bytes, four arrive.
        assert_eq!(dechunk("14\r\nshor"), None);
        assert_eq!(dechunk("not-hex\r\n"), None);
        // A chunk boundary inside a multi-byte character.
        assert_eq!(dechunk("1\r\né\r\n0\r\n\r\n"), None);
    }

    #[test]
    fn the_navigation_script_targets_the_sync_route() {
        // `frontend/src/router.tsx` mounts the page at `/sync`; the shell and
        // the router are one artifact, so this is the one place the path is
        // repeated and it is asserted rather than assumed.
        assert!(NAVIGATE_TO_SYNC_JS.contains("'/sync'"));
        // The router keys its popstate listener on `history.state.idx`, so the
        // existing state must be carried through the push.
        assert!(NAVIGATE_TO_SYNC_JS.contains("window.history.state"));
        assert!(NAVIGATE_TO_SYNC_JS.contains("PopStateEvent"));
    }

    #[test]
    fn the_poll_is_slower_than_the_launch_and_far_slower_than_the_condition() {
        // FR-096's condition is at most hourly and then waits for a person.
        assert!(POLL_INTERVAL >= Duration::from_secs(300));
        assert!(FIRST_POLL_DELAY < POLL_INTERVAL);
    }
}
