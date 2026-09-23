//! The restart policy, as pure functions: how long a restart has to wait for
//! the previous one, when that wait is earned, and the order the running
//! daemon is stopped in before a replacement is spawned.
//!
//! Split out of `daemon.rs` — which holds the IPC commands that call these —
//! to keep every file under the project's 400-line cap (see `.agents/stack.md`).
//! It is also what makes the policy testable: `restart_daemon` needs an
//! `AppHandle` and spawns processes, while everything here is arithmetic and
//! sequencing over injected probes.

/// The rate-limit decision for `restart_daemon` **and** the copy its refusal
/// carries, in one pure function so both are unit-testable without spawning a
/// process. `None` means go ahead; `Some(message)` is the refusal, which
/// states the remaining wait — someone who just pressed Restart needs to know
/// whether to wait or to go looking elsewhere.
///
/// The window is measured from the previous *successful* restart, which is
/// what [`record_restart_outcome`] is careful to record.
pub fn restart_rate_limit_refusal(
    prev: Option<std::time::Instant>,
    now: std::time::Instant,
    min_interval: std::time::Duration,
) -> Option<String> {
    let elapsed = now.duration_since(prev?);
    if elapsed >= min_interval {
        return None;
    }
    let remaining = min_interval
        .as_secs()
        .saturating_sub(elapsed.as_secs())
        .max(1);
    Some(format!("restart_daemon: rate-limited; retry in {remaining}s"))
}

/// Record a restart attempt's outcome against the rate-limit window.
///
/// The window is consumed ONLY by a restart that actually spawned. A failed
/// spawn leaves `window` untouched, so the user may retry at once rather than
/// waiting out a cooldown a failure earned (see "Rate-limit restarts from the
/// last success"). The window is a parameter
/// rather than the static, so that rule is unit-testable.
pub fn record_restart_outcome<T, E>(
    window: &mut Option<std::time::Instant>,
    now: std::time::Instant,
    outcome: &Result<T, E>,
) {
    if outcome.is_ok() {
        *window = Some(now);
    }
}

/// The stop half of a restart, over injected probes so both the ORDER of the
/// steps and the refusal to continue are unit-testable without a real daemon.
///
/// `Ok(Some(port))` — a responsive daemon was asked to shut down and the port
/// was observed free. `Ok(None)` — nothing responsive to stop, so the caller
/// goes straight to spawning. `Err` — a responsive daemon was asked to stop
/// and the port never freed; the caller propagates that instead of spawning a
/// replacement that could not bind (see "Restart by stopping the running daemon
/// first").
pub fn stop_running_daemon<R, P, S, F>(
    read_info: R,
    responds: P,
    shutdown: S,
    port_free: F,
) -> Result<Option<u16>, String>
where
    R: FnOnce() -> Option<(u16, String)>,
    P: FnOnce(u16) -> bool,
    S: FnOnce(u16, &str) -> Result<(), String>,
    F: FnOnce(u16) -> bool,
{
    let Some((port, token)) = read_info() else {
        return Ok(None);
    };
    if !responds(port) {
        return Ok(None);
    }
    shutdown(port, &token)?;
    if !port_free(port) {
        return Err(format!(
            "daemon on port {port} did not stop within 8s of the shutdown request"
        ));
    }
    Ok(Some(port))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    // --- "Rate-limit restarts from the last success": restarts are serialised and rate-limited to
    // one every five seconds, measured from the last SUCCESSFUL restart. ---

    // acceptance(spec = "desktop-app", scenario = "restarts are rate-limited, and a failed spawn does not consume the window")
    #[test]
    fn a_restart_inside_the_window_is_refused_with_the_remaining_wait() {
        let prev = Instant::now();
        let now = prev + Duration::from_secs(2);
        let refusal = restart_rate_limit_refusal(Some(prev), now, Duration::from_secs(5))
            .expect("a restart 2s after the last one is inside the 5s window");
        // The copy has to state the wait: the tray has nowhere to show a
        // progress indicator, so the message is the whole report.
        assert!(refusal.contains("rate-limited"), "{refusal}");
        assert!(refusal.contains("retry in 3s"), "{refusal}");
    }

    #[test]
    fn the_stated_wait_never_rounds_down_to_zero_seconds() {
        // 4.9s elapsed of a 5s window: "retry in 0s" would read as "now".
        let prev = Instant::now();
        let now = prev + Duration::from_millis(4_900);
        let refusal = restart_rate_limit_refusal(Some(prev), now, Duration::from_secs(5)).unwrap();
        assert!(refusal.contains("retry in 1s"), "{refusal}");
    }

    #[test]
    fn not_rate_limited_after_interval() {
        let prev = Instant::now();
        let now = prev + Duration::from_secs(6);
        assert_eq!(
            restart_rate_limit_refusal(Some(prev), now, Duration::from_secs(5)),
            None
        );
    }

    #[test]
    fn not_rate_limited_on_first_call() {
        assert_eq!(
            restart_rate_limit_refusal(None, Instant::now(), Duration::from_secs(5)),
            None
        );
    }

    /// The other half of "Rate-limit restarts from the last success": the window belongs to a
    /// restart that actually spawned. A failed spawn must leave the user free to retry at once
    /// rather than serving out a cooldown its own failure earned.
    // acceptance(spec = "desktop-app", scenario = "restarts are rate-limited, and a failed spawn does not consume the window")
    #[test]
    fn a_failed_spawn_leaves_the_window_unconsumed_so_a_retry_is_allowed() {
        let mut window: Option<Instant> = None;
        let failed: Result<u32, String> = Err("no daemon binary anywhere".to_string());

        let at = Instant::now();
        record_restart_outcome(&mut window, at, &failed);
        assert_eq!(window, None, "a failed spawn must not start the cooldown");

        // ...so the very next request, with no wait at all, is allowed.
        assert_eq!(
            restart_rate_limit_refusal(window, at, Duration::from_secs(5)),
            None
        );

        // A spawn that succeeded DOES consume it, and the next immediate
        // request is refused.
        let ok: Result<u32, String> = Ok(4242);
        record_restart_outcome(&mut window, at, &ok);
        assert_eq!(window, Some(at));
        assert!(restart_rate_limit_refusal(window, at, Duration::from_secs(5)).is_some());
    }

    // --- "Restart by stopping the running daemon first": a restart stops a responsive daemon and
    // observes the port free before spawning a replacement. ---

    /// Records which probe ran, in order, so the sequencing is asserted rather
    /// than assumed.
    #[derive(Default)]
    struct StopCalls(std::cell::RefCell<Vec<&'static str>>);

    impl StopCalls {
        fn note(&self, what: &'static str) {
            self.0.borrow_mut().push(what);
        }
        fn seen(&self) -> Vec<&'static str> {
            self.0.borrow().clone()
        }
    }

    // acceptance(spec = "desktop-app", scenario = "a restart stops the running daemon before spawning a replacement")
    #[test]
    fn a_responsive_daemon_is_shut_down_and_its_port_awaited_before_anything_else() {
        let calls = StopCalls::default();
        let stopped = stop_running_daemon(
            || Some((8000, "tok-123".to_string())),
            |port| {
                calls.note("responds");
                assert_eq!(port, 8000);
                true
            },
            |port, token| {
                calls.note("shutdown");
                assert_eq!(port, 8000);
                // The shutdown route is token-gated; the token has to be the
                // one daemon.json named, not one the shell invented.
                assert_eq!(token, "tok-123");
                Ok(())
            },
            |port| {
                calls.note("port_free");
                assert_eq!(port, 8000);
                true
            },
        );

        assert_eq!(stopped, Ok(Some(8000)));
        assert_eq!(calls.seen(), vec!["responds", "shutdown", "port_free"]);
    }

    /// "A restart that cannot free the port reports that rather than appearing
    /// to succeed" — the caller `?`s this, so the spawn never runs.
    // acceptance(spec = "desktop-app", scenario = "a restart stops the running daemon before spawning a replacement")
    #[test]
    fn a_port_that_never_frees_is_an_error_naming_the_port() {
        let err = stop_running_daemon(
            || Some((8000, "tok".to_string())),
            |_| true,
            |_, _| Ok(()),
            |_| false,
        )
        .unwrap_err();
        assert!(err.contains("8000"), "{err}");
        assert!(err.contains("did not stop"), "{err}");
    }

    #[test]
    fn a_rejected_shutdown_stops_the_restart_rather_than_waiting_on_the_port() {
        let calls = StopCalls::default();
        let err = stop_running_daemon(
            || Some((8000, "stale-token".to_string())),
            |_| true,
            |_, _| Err("shutdown rejected: HTTP/1.1 401 Unauthorized".to_string()),
            |_| {
                calls.note("port_free");
                true
            },
        )
        .unwrap_err();
        assert!(err.contains("401"), "{err}");
        assert!(
            calls.seen().is_empty(),
            "a rejected shutdown must not be followed by a port wait"
        );
    }

    #[test]
    fn nothing_recorded_means_nothing_to_stop() {
        let calls = StopCalls::default();
        let stopped = stop_running_daemon(
            || None,
            |_| {
                calls.note("responds");
                true
            },
            |_, _| {
                calls.note("shutdown");
                Ok(())
            },
            |_| true,
        );
        assert_eq!(stopped, Ok(None));
        assert!(calls.seen().is_empty());
    }

    #[test]
    fn a_recorded_but_unresponsive_daemon_is_not_asked_to_shut_down() {
        // daemon.json outlived its daemon: there is nothing listening to take
        // a shutdown request, so we go straight to spawning.
        let calls = StopCalls::default();
        let stopped = stop_running_daemon(
            || Some((8000, "tok".to_string())),
            |_| false,
            |_, _| {
                calls.note("shutdown");
                Ok(())
            },
            |_| true,
        );
        assert_eq!(stopped, Ok(None));
        assert!(calls.seen().is_empty());
    }
}
