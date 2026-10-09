//! Forcing a wedged daemon out, for an explicit restart.
//!
//! A restart asks for the running daemon to be replaced. When that daemon does
//! not answer, or answers the shutdown request but never lets go of its port,
//! the replacement could only refuse beside it and the wedged process would
//! stay forever. So the restart escalates: `SIGTERM`, a short wait, then
//! `SIGKILL` — but only for the pid this vault's `daemon.json` records, and
//! only once its command line shows it is a Coffer daemon (not the model
//! proxy, not a recycled pid). See spec daemon "Force out a wedged daemon on
//! an explicit restart". The pid `daemon.json` records is the daemon's Python
//! process; in a one-file build its bootloader parent exits with it, and the
//! upstreams it leaves behind are reaped by the next daemon's startup sweep.

use std::process::Command;
use std::time::{Duration, Instant};

use crate::discovery::{read_daemon_pid, wait_for_port_free};

/// How long a `SIGTERM` gets before `SIGKILL`.
const TERM_GRACE: Duration = Duration::from_secs(5);
/// How long the port gets to free once the process is gone.
const PORT_GRACE: Duration = Duration::from_secs(5);

/// Whether a command line names a Coffer daemon: the frozen `coffer-daemon`
/// or a source run of the daemon entry module, and not `coffer-daemon proxy`.
pub fn is_daemon_command(command: &str) -> bool {
    let mut words = command.split_whitespace();
    let program = words.next().unwrap_or("");
    if words.next() == Some("proxy") {
        return false;
    }
    program.ends_with("coffer-daemon") || command.contains("coffer.infrastructure.daemon.entry")
}

#[cfg(unix)]
fn command_of(pid: u32) -> Option<String> {
    let out = Command::new("ps")
        .args(["-o", "command=", "-p", &pid.to_string()])
        .output()
        .ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).trim().to_string())
}

#[cfg(unix)]
fn alive(pid: u32) -> bool {
    // SAFETY: signal 0 only checks the pid can be signalled.
    unsafe { libc::kill(pid as libc::pid_t, 0) == 0 }
}

#[cfg(unix)]
fn signal(pid: u32, sig: libc::c_int) {
    // SAFETY: the pid was checked to be a Coffer daemon just before.
    unsafe {
        libc::kill(pid as libc::pid_t, sig);
    }
}

#[cfg(unix)]
fn wait_gone(pid: u32, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if !alive(pid) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    !alive(pid)
}

/// End the daemon `daemon.json` records, which listens (or listened) on
/// `port`. `Ok(true)` — it was ended and the port is free; `Ok(false)` — no
/// live Coffer daemon is recorded, nothing was touched; `Err` — the port is
/// still held afterwards.
#[cfg(unix)]
pub fn force_stop_recorded_daemon(port: u16) -> Result<bool, String> {
    let Some(pid) = read_daemon_pid() else {
        return Ok(false);
    };
    if !alive(pid) || !command_of(pid).is_some_and(|c| is_daemon_command(&c)) {
        return Ok(false);
    }
    log::warn!("restart: daemon pid {pid} on port {port} is wedged; forcing it out");
    signal(pid, libc::SIGTERM);
    if !wait_gone(pid, TERM_GRACE) {
        signal(pid, libc::SIGKILL);
        wait_gone(pid, TERM_GRACE);
    }
    if wait_for_port_free(port, PORT_GRACE) {
        Ok(true)
    } else {
        Err(format!(
            "daemon on port {port} (pid {pid}) was ended but the port is still held"
        ))
    }
}

#[cfg(not(unix))]
pub fn force_stop_recorded_daemon(_port: u16) -> Result<bool, String> {
    Ok(false)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_frozen_daemon_and_a_source_daemon_are_daemons() {
        assert!(is_daemon_command(
            "/Applications/Coffer.app/Contents/MacOS/coffer-daemon"
        ));
        assert!(is_daemon_command(
            "/usr/bin/python3 -m coffer.infrastructure.daemon.entry"
        ));
    }

    #[test]
    fn the_model_proxy_and_strangers_are_not() {
        assert!(!is_daemon_command(
            "/Users/you/.coffer/bin/coffer-daemon proxy --port 38471"
        ));
        assert!(!is_daemon_command("/usr/bin/grep coffer-daemon notes.txt"));
        assert!(!is_daemon_command(""));
    }
}
