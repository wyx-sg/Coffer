//! The poll that keeps the menu bar true: whether the daemon is serving and how
//! many things on Overview need the user.
//!
//! One light loop over loopback. Every tick reads `daemon.json` and the
//! daemon's own status — the probe `resolve.rs` gates its take-over on — and
//! lets the sync watcher run its own slow poll on a tick that reached it. The
//! attention list is read every 20 seconds, and at once whenever the daemon
//! comes (back) up; while the window is open the page also reports the list's
//! length the moment it changes (`tray::set_attention_count`), so resolving
//! something drops the count at once. A tray
//! action that changes something (a restart) wakes the loop instead of waiting
//! out the tick.

use std::sync::mpsc::{channel, Receiver, Sender};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde_json::Value;
use tauri::{AppHandle, Manager};

use crate::daemon_http::fetch_ok;
use crate::discovery::read_daemon_info;
use crate::sync_watch::SyncWatch;
use crate::tray::update_state;
use crate::tray_state::{Attention, Daemon};

/// How often the daemon's status is read — and so how long the menu bar may
/// lag a daemon going down.
pub const STATUS_TICK: Duration = Duration::from_secs(10);
/// How often the attention list is re-read.
const SLOW_TICK: Duration = Duration::from_secs(20);
/// A short pause before the first tick, so it does not race the launch
/// handshake's detect-or-spawn.
const FIRST_TICK_DELAY: Duration = Duration::from_secs(2);
/// Failed probes before a launching app says "offline" rather than
/// "connecting": a cold daemon takes seconds to answer.
const LAUNCH_GRACE_FAILURES: u32 = 3;

/// The loop's doorbell.
struct Wake(Mutex<Sender<()>>);

/// Start the loop. Runs forever on its own thread.
pub fn start(app: AppHandle) {
    let (tx, rx) = channel();
    app.manage(Wake(Mutex::new(tx)));
    std::thread::spawn(move || run(app, rx));
}

/// Re-read everything now rather than at the next tick.
pub fn refresh(app: &AppHandle) {
    if let Some(wake) = app.try_state::<Wake>() {
        let _ = wake.0.lock().unwrap_or_else(|e| e.into_inner()).send(());
    }
}

fn run(app: AppHandle, wake: Receiver<()>) {
    let mut sync = SyncWatch::default();
    let mut daemon = Daemon::Connecting;
    let mut failures = 0u32;
    let mut slow_read: Option<Instant> = None;
    std::thread::sleep(FIRST_TICK_DELAY);
    loop {
        let probe = read_daemon_info().and_then(|(port, token)| {
            let body = fetch_ok(port, &token, "/api/v1/daemon/status")?;
            Some((port, token, body))
        });
        failures = if probe.is_some() { 0 } else { failures + 1 };
        let was_online = matches!(daemon, Daemon::Running { .. });
        daemon = next_daemon(
            &daemon,
            probe
                .as_ref()
                .map(|(port, _, body)| (*port, parse_version(body))),
            failures,
        );
        let now_daemon = daemon.clone();
        update_state(&app, |s| s.daemon = now_daemon);

        if let Some((port, token, _)) = probe {
            let slow_due = slow_read.is_none_or(|at| at.elapsed() >= SLOW_TICK);
            if !was_online || slow_due {
                slow_read = Some(Instant::now());
                let attention =
                    fetch_ok(port, &token, "/api/v1/attention").and_then(|b| parse_attention(&b));
                update_state(&app, |s| {
                    // A read that failed keeps what was last known.
                    if let Some(a) = attention {
                        s.set_attention(a);
                    }
                });
            }
            sync.tick(&app, port, &token);
        } else if !matches!(daemon, Daemon::Running { .. }) {
            slow_read = None;
        }
        // A doorbell or the tick, whichever is first. A closed channel means
        // the app is going away; the tick keeps the loop honest either way.
        let _ = wake.recv_timeout(STATUS_TICK);
    }
}

/// The daemon's state after one probe: running when it answered, offline once
/// it has not — but a launching app, which has never reached one, allows a
/// cold daemon a few probes before calling it offline.
pub fn next_daemon(prev: &Daemon, answer: Option<(u16, String)>, failures: u32) -> Daemon {
    match answer {
        Some((port, version)) => Daemon::Running { port, version },
        None if matches!(prev, Daemon::Connecting) && failures < LAUNCH_GRACE_FAILURES => {
            Daemon::Connecting
        }
        None => Daemon::Offline,
    }
}

/// `version` from a `GET /api/v1/daemon/status` body; empty when absent.
pub fn parse_version(body: &str) -> String {
    serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|v| v.get("version")?.as_str().map(str::to_owned))
        .unwrap_or_default()
}

/// The count of `items` in `GET /api/v1/attention` — the list the Overview
/// shows, which leaves out what the user has ignored.
pub fn parse_attention(body: &str) -> Option<Attention> {
    let v: Value = serde_json::from_str(body).ok()?;
    let items = v.get("items")?.as_array()?;
    Some(Attention { count: items.len() })
}

#[cfg(test)]
#[path = "tray_watch_tests.rs"]
mod tests;
