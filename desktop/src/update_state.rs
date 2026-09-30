//! What the updater knows and when it asks — the pure half of `updater.rs`
//! (spec desktop-app "Check for updates against a signed release manifest").
//!
//! One status record is the whole interface: the About tab renders it, the
//! menu bar's update entry is labelled from it, and every transition below is
//! a method on it, so the rules — a failed check keeps the last good result, a
//! second press while busy is refused, nothing installs without an update the
//! user was shown — are asserted here rather than hoped for in the glue.

use std::time::{Duration, SystemTime};

/// Checks run at launch and then this often while the app is open.
pub const CHECK_INTERVAL: Duration = Duration::from_secs(6 * 60 * 60);
/// The launch check waits this long, so it neither races the daemon handshake
/// nor runs before the page has said whether the user switched checks off.
pub const FIRST_CHECK_DELAY: Duration = Duration::from_secs(30);
/// How long a check may wait for the manifest (the About board's "timed out
/// after 10 s").
pub const CHECK_TIMEOUT: Duration = Duration::from_secs(10);

/// Where a check or install is.
#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub enum Phase {
    Idle,
    Checking,
    UpToDate,
    Available,
    Downloading,
    Installing,
    Failed,
}

/// A newer release the manifest announced.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AvailableUpdate {
    pub version: String,
    pub notes: Option<String>,
    /// RFC 3339, as the manifest's `pub_date` gave it.
    pub date: Option<String>,
}

/// Why a check or install failed, in the terms the About tab shows.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Failure {
    /// The archive's signature is missing or does not verify against the
    /// public key built into the shell. Never installed.
    Signature(String),
    /// The manifest or archive could not be fetched.
    Network(String),
    Other(String),
}

impl Failure {
    pub fn message(&self) -> String {
        match self {
            Failure::Signature(detail) => format!(
                "The update's signature did not verify, so it was not installed ({detail})."
            ),
            Failure::Network(detail) => {
                format!("Couldn't reach the release manifest on github.com ({detail}).")
            }
            Failure::Other(detail) => detail.clone(),
        }
    }
}

/// The record the About tab and the menu bar are drawn from.
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateStatus {
    /// Whether this build carries an updater public key. A build without one
    /// (every build from source) never checks.
    pub configured: bool,
    pub current_version: String,
    pub phase: Phase,
    /// When the last SUCCESSFUL check finished, in milliseconds since the Unix
    /// epoch. A failed check leaves it where it was.
    pub last_checked_at: Option<u64>,
    pub available: Option<AvailableUpdate>,
    pub error: Option<String>,
    pub downloaded: Option<u64>,
    pub total: Option<u64>,
    /// Whether the launch and six-hourly checks run ("Check automatically").
    pub auto_check: bool,
}

impl UpdateStatus {
    pub fn new(current_version: &str, configured: bool) -> UpdateStatus {
        UpdateStatus {
            configured,
            current_version: current_version.to_owned(),
            phase: Phase::Idle,
            last_checked_at: None,
            available: None,
            error: None,
            downloaded: None,
            total: None,
            auto_check: true,
        }
    }

    /// A check, a download or an install is running: a second press waits.
    pub fn busy(&self) -> bool {
        matches!(
            self.phase,
            Phase::Checking | Phase::Downloading | Phase::Installing
        )
    }

    /// Start a check. `Err` when it cannot start, with the reason.
    pub fn begin_check(&mut self) -> Result<(), String> {
        if !self.configured {
            return Err(NOT_CONFIGURED.to_owned());
        }
        if self.busy() {
            return Err("An update check or download is already running.".to_owned());
        }
        self.phase = Phase::Checking;
        self.error = None;
        Ok(())
    }

    /// Record what a check found. A failure keeps the last successful check's
    /// time and whatever it found, so the About tab still shows them.
    pub fn finish_check(&mut self, now_ms: u64, found: Result<Option<AvailableUpdate>, Failure>) {
        match found {
            Ok(None) => {
                self.phase = Phase::UpToDate;
                self.available = None;
                self.last_checked_at = Some(now_ms);
            }
            Ok(Some(update)) => {
                self.phase = Phase::Available;
                self.available = Some(update);
                self.last_checked_at = Some(now_ms);
            }
            Err(failure) => {
                self.phase = Phase::Failed;
                self.error = Some(failure.message());
            }
        }
    }

    /// Start installing the update a check found. `Err` when there is none, or
    /// something is already running.
    pub fn begin_install(&mut self) -> Result<(), String> {
        if self.busy() {
            return Err("An update check or download is already running.".to_owned());
        }
        if self.available.is_none() {
            return Err("There is no update to install — check for updates first.".to_owned());
        }
        self.phase = Phase::Downloading;
        self.error = None;
        self.downloaded = Some(0);
        self.total = None;
        Ok(())
    }

    pub fn progress(&mut self, chunk: usize, total: Option<u64>) {
        self.downloaded = Some(self.downloaded.unwrap_or(0) + chunk as u64);
        if total.is_some() {
            self.total = total;
        }
    }

    /// The archive downloaded and verified; the `.app` is being replaced.
    pub fn installing(&mut self) {
        self.phase = Phase::Installing;
    }

    /// The install failed. The running version is untouched, and the update
    /// stays on offer so the user can try again.
    pub fn install_failed(&mut self, failure: Failure) {
        self.phase = Phase::Failed;
        self.error = Some(failure.message());
        self.downloaded = None;
        self.total = None;
    }
}

/// What a check on a build with no updater key says.
pub const NOT_CONFIGURED: &str =
    "This build was made without an update key, so it does not check for updates.";

/// Whether the timer should check now: checks are on, and the last attempt —
/// successful or not — was at least [`CHECK_INTERVAL`] ago (or never). Wall
/// time rather than an `Instant`, which stops while a Mac sleeps: a laptop
/// that sleeps overnight should check when it wakes, not six awake hours on.
pub fn check_due(auto_check: bool, last_attempt: Option<SystemTime>, now: SystemTime) -> bool {
    auto_check
        && last_attempt
            .is_none_or(|at| now.duration_since(at).unwrap_or(Duration::ZERO) >= CHECK_INTERVAL)
}

/// Milliseconds since the Unix epoch, for `last_checked_at`.
pub fn epoch_ms(at: SystemTime) -> u64 {
    at.duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[cfg(test)]
#[path = "update_state_tests.rs"]
mod tests;
