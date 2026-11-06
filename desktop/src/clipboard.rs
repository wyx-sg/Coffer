//! Copying a revealed secret: onto the general pasteboard, marked as concealed
//! and transient, and taken off again after `CLEAR_AFTER` unless something else
//! was copied since.
//!
//! The markers are the nspasteboard.org conventions clipboard managers honour
//! (`org.nspasteboard.ConcealedType`: don't show or keep it;
//! `org.nspasteboard.TransientType`: don't record it in history). The page's own
//! `navigator.clipboard.writeText` can set neither, and leaves the value on the
//! pasteboard until something replaces it, so the reveal dialogs copy through
//! this command instead (spec secret "Release plaintext only to a present
//! human in the desktop app").

use tauri::AppHandle;

/// How long a copied secret stays on the pasteboard. 1Password's default.
#[cfg(target_os = "macos")]
const CLEAR_AFTER: std::time::Duration = std::time::Duration::from_secs(90);

#[tauri::command]
pub fn copy_secret(app: AppHandle, value: String) -> Result<(), String> {
    imp::copy(&app, value)
}

#[cfg(target_os = "macos")]
mod imp {
    use objc2::rc::Retained;
    use objc2::runtime::{AnyObject, Bool};
    use objc2::{class, msg_send};
    use objc2_foundation::NSString;
    use tauri::AppHandle;

    use super::CLEAR_AFTER;

    const STRING_TYPE: &str = "public.utf8-plain-text";
    const MARKERS: [&str; 2] = ["org.nspasteboard.ConcealedType", "org.nspasteboard.TransientType"];

    /// The general pasteboard. Only called on the main thread.
    fn general() -> Retained<AnyObject> {
        // SAFETY: `+[NSPasteboard generalPasteboard]` returns the shared
        // instance (autoreleased); `msg_send!` retains it for us.
        unsafe { msg_send![class!(NSPasteboard), generalPasteboard] }
    }

    fn change_count(board: &AnyObject) -> isize {
        // SAFETY: `-changeCount` takes nothing and returns NSInteger.
        unsafe { msg_send![board, changeCount] }
    }

    /// Put `value` on the pasteboard with the markers; the change count it left.
    fn write(value: &str) -> Result<isize, String> {
        let board = general();
        // SAFETY: documented NSPasteboard selectors with the argument types
        // given; every NSString lives until the call returns.
        unsafe {
            let _: isize = msg_send![&*board, clearContents];
            let text = NSString::from_str(value);
            let kind = NSString::from_str(STRING_TYPE);
            let ok: Bool = msg_send![&*board, setString: &*text, forType: &*kind];
            if !ok.as_bool() {
                return Err("the pasteboard refused the value".to_owned());
            }
            let empty = NSString::from_str("");
            for marker in MARKERS {
                let kind = NSString::from_str(marker);
                let _: Bool = msg_send![&*board, setString: &*empty, forType: &*kind];
            }
        }
        Ok(change_count(&board))
    }

    /// Clear the pasteboard if it still holds what `write` left.
    fn clear_if_unchanged(written: isize) {
        let board = general();
        if change_count(&board) == written {
            // SAFETY: `-clearContents` takes nothing and returns NSInteger.
            let _: isize = unsafe { msg_send![&*board, clearContents] };
        }
    }

    pub fn copy(app: &AppHandle, value: String) -> Result<(), String> {
        let (tx, rx) = std::sync::mpsc::channel();
        app.run_on_main_thread(move || {
            let _ = tx.send(write(&value));
        })
        .map_err(|e| e.to_string())?;
        let written = rx.recv().map_err(|e| e.to_string())??;
        let later = app.clone();
        std::thread::spawn(move || {
            std::thread::sleep(CLEAR_AFTER);
            let _ = later.run_on_main_thread(move || clear_if_unchanged(written));
        });
        Ok(())
    }
}

#[cfg(not(target_os = "macos"))]
mod imp {
    use tauri::AppHandle;

    /// Not a Mac: the page falls back to its own clipboard write.
    pub fn copy(_app: &AppHandle, _value: String) -> Result<(), String> {
        Err("copying a secret through the shell is macOS only".to_owned())
    }
}
