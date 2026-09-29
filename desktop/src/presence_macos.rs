//! The Objective-C half of `presence.rs`: LocalAuthentication for the check
//! itself, and — development builds only — an `NSAlert` in the app window.
//!
//! Plain `msg_send!` against runtime classes rather than generated bindings:
//! the shell calls four selectors, and a bindings crate per framework would be
//! more surface than the calls it wraps.

use std::sync::mpsc;

use block2::RcBlock;
use objc2::rc::Retained;
use objc2::runtime::{AnyObject, Bool};
use objc2::{class, msg_send};
use objc2_foundation::{NSError, NSString};
use tauri::AppHandle;

use super::NativeOutcome;

// `LAContext` lives in LocalAuthentication.framework, which nothing else in
// the app links; the class lookup below would find nothing without this.
#[link(name = "LocalAuthentication", kind = "framework")]
extern "C" {}

/// `LAPolicyDeviceOwnerAuthentication`: biometrics, a paired watch, or the
/// login password — the policy that works on every Mac with a password.
const LA_POLICY_DEVICE_OWNER_AUTHENTICATION: isize = 2;

/// `NSAlertFirstButtonReturn` — the first button added, here "Confirm".
const NS_ALERT_FIRST_BUTTON_RETURN: isize = 1000;

/// Run one check on a context created for it and dropped after it. Blocks the
/// calling thread until the person answers; LocalAuthentication delivers the
/// reply on a queue of its own, so this must not be the main thread.
pub fn evaluate(reason: &str) -> NativeOutcome {
    // SAFETY: `LAContext` is an NSObject subclass; `new` returns +1, which
    // `msg_send!` wraps in `Retained`. Both selectors are LAContext's
    // documented API with the argument types given.
    unsafe {
        let context: Retained<AnyObject> = msg_send![class!(LAContext), new];
        let can: Result<(), Retained<NSError>> = msg_send![
            &*context,
            canEvaluatePolicy: LA_POLICY_DEVICE_OWNER_AUTHENTICATION,
            error: _
        ];
        if let Err(error) = can {
            return NativeOutcome::Unavailable(error.localizedDescription().to_string());
        }

        let (tx, rx) = mpsc::channel::<Result<(), (isize, String)>>();
        let reply = RcBlock::new(move |success: Bool, error: *mut NSError| {
            let outcome = if success.as_bool() {
                Ok(())
            } else {
                // SAFETY: the reply's error is either nil or a valid NSError
                // for the duration of the block.
                match error.as_ref() {
                    Some(e) => Err((e.code(), e.localizedDescription().to_string())),
                    None => Err((0, "no reason given".to_owned())),
                }
            };
            let _ = tx.send(outcome);
        });
        let text = NSString::from_str(reason);
        let _: () = msg_send![
            &*context,
            evaluatePolicy: LA_POLICY_DEVICE_OWNER_AUTHENTICATION,
            localizedReason: &*text,
            reply: &*reply
        ];
        let answer = rx.recv();
        // Dropped here, after the reply: the context lives for exactly one
        // operation, so no later call can ride on this approval.
        drop(context);
        match answer {
            Ok(Ok(())) => NativeOutcome::Approved,
            Ok(Err((code, description))) => NativeOutcome::Failed { code, description },
            Err(_) => NativeOutcome::Failed {
                code: 0,
                description: "LocalAuthentication never replied".to_owned(),
            },
        }
    }
}

/// DEVELOPMENT BUILDS ONLY (`presence::choose_path` decides): a modal alert in
/// the app with the same text and Confirm / Cancel. AppKit must be driven from
/// the main thread, so the alert is posted there and this thread waits.
pub fn confirm_in_window(app: &AppHandle, reason: &str) -> Result<bool, String> {
    let (tx, rx) = mpsc::channel::<bool>();
    let message = reason.to_owned();
    app.run_on_main_thread(move || {
        let _ = tx.send(run_alert(&message));
    })
    .map_err(|e| format!("cannot show the confirmation: {e}"))?;
    rx.recv()
        .map_err(|_| "the confirmation closed without an answer".to_owned())
}

fn run_alert(message: &str) -> bool {
    // SAFETY: called on the main thread (see `confirm_in_window`). NSAlert and
    // NSApplication are AppKit classes the Tauri runtime has already loaded;
    // every selector is their documented API.
    unsafe {
        let application: *mut AnyObject = msg_send![class!(NSApplication), sharedApplication];
        if let Some(application) = application.as_ref() {
            let _: () = msg_send![application, activateIgnoringOtherApps: Bool::YES];
        }
        let alert: Retained<AnyObject> = msg_send![class!(NSAlert), new];
        let title = NSString::from_str(message);
        let detail = NSString::from_str(
            "This Mac has no Touch ID or password check available, so this development \
             build asks here instead. A development build cannot keep other programs \
             from forging this approval.",
        );
        let _: () = msg_send![&*alert, setMessageText: &*title];
        let _: () = msg_send![&*alert, setInformativeText: &*detail];
        let confirm = NSString::from_str("Confirm");
        let cancel = NSString::from_str("Cancel");
        let _: *mut AnyObject = msg_send![&*alert, addButtonWithTitle: &*confirm];
        let _: *mut AnyObject = msg_send![&*alert, addButtonWithTitle: &*cancel];
        let response: isize = msg_send![&*alert, runModal];
        response == NS_ALERT_FIRST_BUTTON_RETURN
    }
}
