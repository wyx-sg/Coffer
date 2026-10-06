//! Keep the macOS traffic lights where `trafficLightPosition` puts them.
//!
//! The title strip (`WindowTitleStrip.tsx`) centres its controls on y 19 and
//! starts them 8px after the lights, which only lines up while the lights sit
//! at the configured inset (`tauri.macos.conf.json`, x 20 y 17). Tauri applies
//! that inset once at creation and again only from the `drawRect:` of a view
//! the webview covers, which AppKit rarely redraws. Whenever AppKit lays the
//! title bar out again (the window hidden to the tray and shown, a sheet or the
//! Touch ID prompt taking key, a resize, leaving full screen) the lights drop
//! back to the system's spot, about 5px higher and 12px further left than the
//! strip's buttons.
//!
//! So the shell puts them back itself: on every window event that can follow
//! such a layout (again a moment later after leaving full screen, whose last
//! layout comes after the notification), and whenever the close button or its
//! title bar container reports a frame change, re-watching those views when
//! AppKit swaps them. Putting them back is idempotent, so the frame
//! change it causes ends there.

#![cfg_attr(not(target_os = "macos"), allow(dead_code))]

/// A view's frame in AppKit coordinates (origin bottom-left, logical points).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Frame {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

/// Where the inset puts the title bar container and the three buttons: the
/// container is the close button's height plus `y` tall, pinned to the window's
/// top edge, so the button (vertically centred in it by AppKit) sits `y` down;
/// the buttons keep their spacing and start at `x`.
pub fn layout(
    inset: (f64, f64),
    window_height: f64,
    container: Frame,
    close: Frame,
    spacing: f64,
) -> (Frame, [f64; 3]) {
    let (x, y) = inset;
    let height = close.height + y;
    let container = Frame {
        y: window_height - height,
        height,
        ..container
    };
    (container, [x, x + spacing, x + 2.0 * spacing])
}

/// The title strip's centre line, px from the window's top edge: half the
/// 38px `--titlebar-inset` (index.css).
pub const STRIP_CENTRE: f64 = 19.0;

/// The bottom edge, in window coordinates (origin bottom-left), that centres a
/// button `height` tall on the strip's centre line. Resizing the container is
/// not enough on its own: on current macOS the buttons keep their own y in it
/// and stay at the system's height, so the shell places them on y itself.
pub fn button_bottom(window_height: f64, height: f64) -> f64 {
    window_height - STRIP_CENTRE - height / 2.0
}

/// Whether two coordinates are the same point on screen.
pub fn same(a: f64, b: f64) -> bool {
    (a - b).abs() < 0.5
}

#[cfg(target_os = "macos")]
pub use macos::{pin, watch};

#[cfg(target_os = "macos")]
mod macos {
    use std::cell::RefCell;
    use std::ptr::NonNull;

    use block2::RcBlock;
    use objc2::msg_send;
    use objc2::rc::Retained;
    use objc2::runtime::AnyObject;
    use objc2_foundation::{NSPoint, NSRect, NSSize, NSString};
    use tauri::{Manager, Runtime, WebviewWindow};

    use super::{button_bottom, layout, same, Frame};

    #[link(name = "AppKit", kind = "framework")]
    extern "C" {
        static NSViewFrameDidChangeNotification: &'static NSString;
        static NSWindowDidExitFullScreenNotification: &'static NSString;
        static NSWindowDidEndLiveResizeNotification: &'static NSString;
        static NSWindowDidBecomeKeyNotification: &'static NSString;
    }

    /// `NSWindowStyleMaskFullScreen`: in full screen the lights are hidden and
    /// AppKit owns the title bar it slides down, so they are left alone.
    const STYLE_MASK_FULL_SCREEN: usize = 1 << 14;

    /// The configured inset for this window, if it has one.
    fn inset<R: Runtime>(window: &WebviewWindow<R>) -> Option<(f64, f64)> {
        window
            .config()
            .app
            .windows
            .iter()
            .find(|w| w.label == window.label())
            .and_then(|w| w.traffic_light_position.as_ref())
            .map(|p| (p.x, p.y))
    }

    fn to_frame(r: NSRect) -> Frame {
        Frame {
            x: r.origin.x,
            y: r.origin.y,
            width: r.size.width,
            height: r.size.height,
        }
    }

    fn to_rect(f: Frame) -> NSRect {
        NSRect::new(NSPoint::new(f.x, f.y), NSSize::new(f.width, f.height))
    }

    /// The close, minimise and zoom buttons, if the window has them.
    unsafe fn buttons(ns_window: &AnyObject) -> Option<[Retained<AnyObject>; 3]> {
        let get = |kind: usize| -> Option<Retained<AnyObject>> {
            msg_send![ns_window, standardWindowButton: kind]
        };
        Some([get(0)?, get(1)?, get(2)?])
    }

    unsafe fn container_of(close: &AnyObject) -> Option<Retained<AnyObject>> {
        let parent: Option<Retained<AnyObject>> = msg_send![close, superview];
        msg_send![&*parent?, superview]
    }

    /// Move the lights to `inset` unless they are already there, and make sure
    /// the views AppKit is using now are watched. Main thread.
    unsafe fn apply(address: usize, inset: (f64, f64)) {
        let ns_window = &*(address as *const AnyObject);
        let style: usize = msg_send![ns_window, styleMask];
        if style & STYLE_MASK_FULL_SCREEN != 0 {
            return;
        }
        let Some([close, mini, zoom]) = buttons(ns_window) else {
            return;
        };
        let Some(container) = container_of(&close) else {
            return;
        };
        observe_frame(&close, address, inset);
        observe_frame(&container, address, inset);
        let close_frame: NSRect = msg_send![&*close, frame];
        let mini_frame: NSRect = msg_send![&*mini, frame];
        let container_frame: NSRect = msg_send![&*container, frame];
        let window_frame: NSRect = msg_send![ns_window, frame];
        let spacing = mini_frame.origin.x - close_frame.origin.x;
        let (target, xs) = layout(
            inset,
            window_frame.size.height,
            to_frame(container_frame),
            to_frame(close_frame),
            spacing,
        );
        let current = to_frame(container_frame);
        if !same(current.y, target.y) || !same(current.height, target.height) {
            let _: () = msg_send![&*container, setFrame: to_rect(target)];
        }
        for (button, x) in [close, mini, zoom].iter().zip(xs) {
            let frame: NSRect = msg_send![&**button, frame];
            // The button's spot in window coordinates, converted into its
            // superview's, which handles a flipped superview too.
            let in_window = NSRect::new(
                NSPoint::new(
                    0.0,
                    button_bottom(window_frame.size.height, frame.size.height),
                ),
                frame.size,
            );
            let Some(parent): Option<Retained<AnyObject>> = msg_send![&**button, superview] else {
                continue;
            };
            let local: NSRect =
                msg_send![&*parent, convertRect: in_window, fromView: None::<&AnyObject>];
            if !same(frame.origin.x, x) || !same(frame.origin.y, local.origin.y) {
                let origin = NSPoint::new(x, local.origin.y);
                let _: () = msg_send![&**button, setFrameOrigin: origin];
            }
        }
    }

    /// Apply now and again once AppKit's pending layout and animation have
    /// run: leaving full screen lays the title bar out after the
    /// notification that says it ended.
    unsafe fn apply_now_and_after(address: usize, inset: (f64, f64)) {
        apply(address, inset);
        for delay in [0.0_f64, 0.3] {
            let block = RcBlock::new(move |_timer: NonNull<AnyObject>| {
                apply(address, inset);
            });
            let _: Retained<AnyObject> = msg_send![
                objc2::class!(NSTimer),
                scheduledTimerWithTimeInterval: delay,
                repeats: false,
                block: &*block
            ];
        }
    }

    fn center() -> Retained<AnyObject> {
        // SAFETY: `defaultCenter` is a class method returning the shared center.
        unsafe { msg_send![objc2::class!(NSNotificationCenter), defaultCenter] }
    }

    thread_local! {
        /// Views already watched. Held, so a freed view's address is never
        /// mistaken for a new view's.
        static OBSERVED: RefCell<Vec<Retained<AnyObject>>> = const { RefCell::new(Vec::new()) };
    }

    /// Re-apply whenever `view`'s frame changes. AppKit can swap the title
    /// bar's views (leaving full screen does), so this is called for whatever
    /// views are current on every apply and skips the ones already watched.
    unsafe fn observe_frame(view: &Retained<AnyObject>, address: usize, inset: (f64, f64)) {
        let seen = OBSERVED.with(|o| {
            o.borrow()
                .iter()
                .any(|v| Retained::as_ptr(v) == Retained::as_ptr(view))
        });
        if seen {
            return;
        }
        OBSERVED.with(|o| o.borrow_mut().push(view.clone()));
        let _: () = msg_send![&**view, setPostsFrameChangedNotifications: true];
        observe(NSViewFrameDidChangeNotification, view, move || {
            apply(address, inset)
        });
    }

    /// Run `then` on the main thread each time `object` posts `name`.
    unsafe fn observe(name: &NSString, object: &AnyObject, then: impl Fn() + 'static) {
        let block = RcBlock::new(move |_note: NonNull<AnyObject>| then());
        let token: Retained<AnyObject> = msg_send![
            &*center(),
            addObserverForName: name,
            object: object,
            queue: None::<&AnyObject>,
            usingBlock: &*block
        ];
        // The center holds the observer for the app's lifetime.
        std::mem::forget(token);
    }

    /// Put the lights back on the main thread, after whatever layout pass is
    /// running now.
    pub fn pin<R: Runtime>(window: &WebviewWindow<R>) {
        let Some(inset) = inset(window) else {
            return;
        };
        let target = window.clone();
        let _ = window.run_on_main_thread(move || {
            if let Ok(ptr) = target.ns_window() {
                // SAFETY: `ns_window` is the window's live NSWindow, and this
                // runs on the main thread, where AppKit must be called.
                unsafe { apply(ptr as usize, inset) };
            }
        });
    }

    /// Put the lights back whenever AppKit moves them: observe frame changes
    /// of the close button and of its title bar container, and the window
    /// leaving full screen, finishing a live resize or becoming key. Call
    /// once, from setup, on the main thread.
    pub fn watch<R: Runtime>(window: &WebviewWindow<R>) {
        let Some(inset) = inset(window) else {
            return;
        };
        let Ok(ptr) = window.ns_window() else {
            return;
        };
        let address = ptr as usize;
        // SAFETY: setup runs on the main thread; the window is never destroyed
        // (close hides it to the tray), so its address stays valid for the
        // observers' lifetime, which is the app's.
        unsafe {
            let ns_window = &*(address as *const AnyObject);
            for name in [
                NSWindowDidExitFullScreenNotification,
                NSWindowDidEndLiveResizeNotification,
                NSWindowDidBecomeKeyNotification,
            ] {
                observe(name, ns_window, move || apply_now_and_after(address, inset));
            }
            apply(address, inset);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const CLOSE: Frame = Frame {
        x: 7.0,
        y: 6.0,
        width: 14.0,
        height: 16.0,
    };
    const CONTAINER: Frame = Frame {
        x: 0.0,
        y: 872.0,
        width: 1440.0,
        height: 28.0,
    };

    /// x 20 y 17 (tauri.macos.conf.json) gives a 33px container on the top
    /// edge, which puts the close button's 16px frame at y 17 and the lights'
    /// centre at y 19, the strip's centre line.
    #[test]
    fn the_configured_inset_centres_the_lights_on_the_strip() {
        let (container, xs) = layout((20.0, 17.0), 900.0, CONTAINER, CLOSE, 20.0);
        assert_eq!(container.height, 33.0);
        assert_eq!(container.y, 900.0 - 33.0);
        assert_eq!(container.width, CONTAINER.width);
        assert_eq!(xs, [20.0, 40.0, 60.0]);
    }

    #[test]
    fn the_layout_follows_the_window_height() {
        let (container, _) = layout((20.0, 17.0), 600.0, CONTAINER, CLOSE, 20.0);
        assert_eq!(container.y, 567.0);
    }

    /// A 16px close frame centred on y 19 spans 11..27 from the top.
    #[test]
    fn a_button_is_centred_on_the_strip() {
        assert_eq!(button_bottom(900.0, 16.0), 900.0 - 27.0);
        assert_eq!(button_bottom(600.0, 14.0), 600.0 - 26.0);
    }

    #[test]
    fn sub_pixel_differences_are_the_same_spot() {
        assert!(same(20.0, 20.2));
        assert!(!same(20.0, 8.0));
    }

    /// The strip's numbers (WindowTitleStrip.tsx, index.css) are derived from
    /// this inset; changing it unaligns them.
    #[test]
    fn the_config_keeps_the_inset_the_strip_is_drawn_for() {
        let conf: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.macos.conf.json")).unwrap();
        let p = &conf["app"]["windows"][0]["trafficLightPosition"];
        assert_eq!((p["x"].as_f64(), p["y"].as_f64()), (Some(20.0), Some(17.0)));
    }
}
