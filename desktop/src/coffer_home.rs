//! Every path under `~/.coffer` the shell touches — the only place in the
//! crate that knows them. The layout itself belongs to the daemon
//! (`backend/coffer/infrastructure/vault/home.py`); these are the entries the
//! shell reads or writes before a daemon is there to ask.
//!
//! Each function is pure over the home directory, so the layout is testable
//! without touching the real one; `home_dir` is the one environment read.

use std::env;
use std::path::{Path, PathBuf};

/// The user's home: `HOME`, else `USERPROFILE`.
pub fn home_dir() -> Option<String> {
    env::var("HOME")
        .ok()
        .or_else(|| env::var("USERPROFILE").ok())
}

/// `~/.coffer` for `home`.
pub fn coffer_home(home: impl AsRef<Path>) -> PathBuf {
    home.as_ref().join(".coffer")
}

/// `~/.coffer/daemon.json` — the running daemon's port and token.
pub fn daemon_json(home: impl AsRef<Path>) -> PathBuf {
    coffer_home(home).join("daemon.json")
}

/// `~/.coffer/bin` — where the daemon deploys the frozen binaries.
pub fn bin_dir(home: impl AsRef<Path>) -> PathBuf {
    coffer_home(home).join("bin")
}

/// `~/.coffer/logs` — the daemon's log directory.
pub fn logs_dir(home: impl AsRef<Path>) -> PathBuf {
    coffer_home(home).join("logs")
}

/// `~/.coffer/master.key` — the development arrangement's key file.
pub fn master_key(home: impl AsRef<Path>) -> PathBuf {
    coffer_home(home).join("master.key")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_entry_sits_under_the_coffer_home() {
        assert_eq!(coffer_home("/h"), PathBuf::from("/h/.coffer"));
        assert_eq!(daemon_json("/h"), PathBuf::from("/h/.coffer/daemon.json"));
        assert_eq!(bin_dir("/h"), PathBuf::from("/h/.coffer/bin"));
        assert_eq!(logs_dir("/h"), PathBuf::from("/h/.coffer/logs"));
        assert_eq!(master_key("/h"), PathBuf::from("/h/.coffer/master.key"));
    }
}
