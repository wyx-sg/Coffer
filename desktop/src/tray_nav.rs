//! Bringing the window up on a page — what the menu bar's items do.
//!
//! The frontend is one `createBrowserRouter` over `frontend/dist` (spec
//! desktop-app "Consume the one frontend build the daemon serves"), so the
//! shell navigates it the way the browser's back button does: push the entry,
//! then let the router's own `popstate` listener read it, rather than giving
//! the page a second code path to be told where to go. React Router keeps
//! `{usr, key, idx}` in `history.state` and keys its listener on `idx`, so the
//! entry pushed carries the next `idx`.

use tauri::{AppHandle, Manager};

/// Show, focus and un-minimise the window, without moving it.
pub fn show_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
        let _ = window.unminimize();
    }
}

/// Show the window on `path`.
pub fn open_page(app: &AppHandle, path: &str) {
    navigate(app, &navigate_js(path));
}

fn navigate(app: &AppHandle, script: &str) {
    show_window(app);
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.eval(script);
    }
}

/// A push of `path` the router reads as a navigation.
pub fn navigate_js(path: &str) -> String {
    let path = js_string(path);
    format!(
        "(function(){{var s=window.history.state||{{}};\
         var n={{usr:null,key:'tray'+Date.now(),idx:(s.idx||0)+1}};\
         window.history.pushState(n,'',{path});\
         window.dispatchEvent(new PopStateEvent('popstate',{{state:n}}));}})()"
    )
}

/// `text` as a single-quoted JavaScript string literal.
fn js_string(text: &str) -> String {
    let mut out = String::from("'");
    for c in text.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\'' => out.push_str("\\'"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '<' => out.push_str("\\x3c"),
            c => out.push(c),
        }
    }
    out.push('\'');
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_navigation_pushes_the_path_and_tells_the_router() {
        let js = navigate_js("/conversations");
        assert!(js.contains("pushState(n,'','/conversations')"), "{js}");
        assert!(js.contains("PopStateEvent('popstate'"));
        // The router ignores an entry without the next `idx`.
        assert!(js.contains("idx:(s.idx||0)+1"));
    }

    #[test]
    fn a_path_cannot_break_out_of_its_string() {
        assert_eq!(js_string("a'b\\c"), "'a\\'b\\\\c'");
        let js = navigate_js("/x');alert(1);('");
        assert!(js.contains(r"pushState(n,'','/x\');alert(1);(\'')"), "{js}");
    }
}
