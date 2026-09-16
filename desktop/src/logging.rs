//! The shell's own log records, and the file they go to.
//!
//! Five `log::` call sites in this crate report things a user has no other way
//! to see — which binary the five-step chain picked, that a restart asked from
//! the tray failed. The `log` facade drops every record until a logger is
//! installed, so until this module existed a failed tray restart failed in
//! silence, on the one surface a user reaches when the daemon is down and the
//! web UI is therefore unreachable.
//!
//! Records land in `~/.coffer/logs/daemon.log`: the file this shell already
//! redirects a spawned daemon's own stdout to (`spawn.rs`), the file every
//! "check `~/.coffer/logs/daemon.log`" message in the CLI points at, and the
//! file both the Activity page's daemon-log tab and `coffer__diagnose` read.
//! A separate `desktop.log` would be a second place to look that nothing tells
//! anyone about.
//!
//! They are written as one-line structlog-shaped JSON because that reader
//! (`backend/coffer/application/log_reader.py`) lifts `timestamp` / `level` /
//! `logger` / `event` onto its own columns for a line it recognises, and dumps
//! anything else whole into the message cell. The file is already several
//! writers' worth of formats; this is the one it reads best.

use std::env;
use std::fs;
use std::io::Write;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use log::{Level, LevelFilter, Log, Metadata, Record};

/// The `logger` field on every record this shell writes, so a reader can tell
/// the shell's lines from the daemon's in a file both append to.
const LOGGER_NAME: &str = "coffer.desktop";

/// Path the shell's records — and a spawned daemon's stdout/stderr — are
/// appended to, given the user's home dir. Pure so it's unit-testable.
/// Mirrors the CLI spawn (backend `_client.py`), which logs to this same file.
pub fn daemon_log_path(home: &str) -> PathBuf {
    PathBuf::from(home)
        .join(".coffer")
        .join("logs")
        .join("daemon.log")
}

/// Open `~/.coffer/logs/daemon.log` for appending, creating the logs directory
/// if needed. Returns `None` on any failure (no home, mkdir/open error) so
/// callers degrade — `spawn.rs` to `/dev/null`, the logger to dropping the
/// record — rather than failing the thing they were asked to do.
pub fn open_daemon_log() -> Option<fs::File> {
    let home = env::var("HOME")
        .ok()
        .or_else(|| env::var("USERPROFILE").ok())?;
    let path = daemon_log_path(&home);
    fs::create_dir_all(path.parent()?).ok()?;
    fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .ok()
}

/// Install this logger as the process-wide `log` implementation.
///
/// Idempotent and infallible on purpose: `set_logger` refuses a second call,
/// and a shell that cannot log is still a shell that should open its window.
pub fn install() {
    static LOGGER: FileLogger = FileLogger;
    if log::set_logger(&LOGGER).is_ok() {
        log::set_max_level(LevelFilter::Info);
    }
}

struct FileLogger;

impl Log for FileLogger {
    fn enabled(&self, metadata: &Metadata) -> bool {
        metadata.level() <= Level::Info
    }

    fn log(&self, record: &Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        // Re-open per record rather than holding a handle for the app's
        // lifetime: these records are rare (a spawn, a restart), and an
        // append-mode open each time follows the file if it is rotated or
        // deleted under us instead of writing into a vanished inode.
        let Some(mut file) = open_daemon_log() else {
            return;
        };
        let _ = append_record(
            &mut file,
            SystemTime::now(),
            record.level(),
            &record.args().to_string(),
        );
    }

    fn flush(&self) {}
}

/// Append one record to `sink` as a single line.
///
/// Split out of `Log::log` so a test can read back the exact bytes that reach
/// the file without setting `$HOME` or installing a process-wide logger. One
/// `writeln` per record, into a file opened `O_APPEND`, so a line of the
/// shell's never lands inside a line of the daemon's — the two processes share
/// this file.
fn append_record(
    sink: &mut impl Write,
    now: SystemTime,
    level: Level,
    event: &str,
) -> std::io::Result<()> {
    writeln!(sink, "{}", json_line(&rfc3339_utc(now), level, event))
}

/// structlog's own lowercase vocabulary, so a level read off this shell's line
/// and one read off the daemon's land on the same word in the same column.
fn level_name(level: Level) -> &'static str {
    match level {
        Level::Error => "error",
        Level::Warn => "warning",
        Level::Info => "info",
        Level::Debug => "debug",
        Level::Trace => "debug",
    }
}

/// One record as a line of JSON. Built through `serde_json` rather than
/// `format!` so a message containing a quote or a newline cannot produce a
/// line the reader then keeps verbatim as `raw`.
fn json_line(timestamp: &str, level: Level, event: &str) -> String {
    serde_json::json!({
        "timestamp": timestamp,
        "level": level_name(level),
        "logger": LOGGER_NAME,
        "event": event,
    })
    .to_string()
}

/// A `SystemTime` as an RFC 3339 UTC timestamp (`2026-09-16T08:12:03.123Z`) —
/// the shape structlog writes and the reader parses.
///
/// Hand-rolled because the alternative is a date crate, and this crate's
/// dependency list is short deliberately (see `Cargo.toml`). A clock before
/// the epoch yields the epoch rather than an error: a wrong timestamp on a
/// diagnostic line is better than no line.
fn rfc3339_utc(now: SystemTime) -> String {
    let since_epoch = now.duration_since(UNIX_EPOCH).unwrap_or_default();
    let secs = since_epoch.as_secs();
    let (year, month, day) = civil_from_days((secs / 86_400) as i64);
    let tod = secs % 86_400;
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{:03}Z",
        tod / 3600,
        (tod / 60) % 60,
        tod % 60,
        since_epoch.subsec_millis(),
    )
}

/// Days since 1970-01-01 as `(year, month, day)` — Howard Hinnant's
/// `civil_from_days`, exact for every date a `SystemTime` can express, leap
/// years and centuries included.
fn civil_from_days(days: i64) -> (i64, u64, u64) {
    // Shift the epoch to 0000-03-01 so a leap day is the last day of a year.
    let z = days + 719_468;
    let era = (if z >= 0 { z } else { z - 146_096 }) / 146_097;
    let day_of_era = (z - era * 146_097) as u64; // [0, 146096]
    let year_of_era =
        (day_of_era - day_of_era / 1460 + day_of_era / 36_524 - day_of_era / 146_096) / 365; // [0, 399]
    let year = year_of_era as i64 + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100); // [0, 365]
    let month_shifted = (5 * day_of_year + 2) / 153; // [0, 11], March = 0
    let day = day_of_year - (153 * month_shifted + 2) / 5 + 1; // [1, 31]
    let month = if month_shifted < 10 {
        month_shifted + 3
    } else {
        month_shifted - 9
    };
    (if month <= 2 { year + 1 } else { year }, month, day)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn daemon_log_path_is_under_coffer_logs() {
        // The shell's records and a spawned daemon's stdout/stderr share this
        // file instead of /dev/null, so a GUI-spawned daemon's crash and a
        // failed tray restart are both recoverable. Mirrors the CLI spawn
        // (backend _client.py), which logs to the same file.
        assert_eq!(
            daemon_log_path("/Users/u"),
            PathBuf::from("/Users/u/.coffer/logs/daemon.log")
        );
    }

    #[test]
    fn epoch_formats_as_rfc3339() {
        assert_eq!(rfc3339_utc(UNIX_EPOCH), "1970-01-01T00:00:00.000Z");
    }

    #[test]
    fn a_known_instant_formats_as_rfc3339() {
        // 2026-09-16T08:12:03.123Z
        let t = UNIX_EPOCH + Duration::new(1_789_546_323, 123_000_000);
        assert_eq!(rfc3339_utc(t), "2026-09-16T08:12:03.123Z");
    }

    #[test]
    fn leap_day_is_not_off_by_one() {
        // 2024-02-29T23:59:59Z — the date arithmetic's failure mode is a
        // one-day slip that only shows up in a leap year.
        let t = UNIX_EPOCH + Duration::from_secs(1_709_251_199);
        assert_eq!(rfc3339_utc(t), "2024-02-29T23:59:59.000Z");
    }

    #[test]
    fn a_pre_epoch_clock_does_not_panic() {
        let t = UNIX_EPOCH - Duration::from_secs(60);
        assert_eq!(rfc3339_utc(t), "1970-01-01T00:00:00.000Z");
    }

    #[test]
    fn a_record_is_one_line_of_parseable_json() {
        let line = json_line(
            "2026-09-16T08:12:03.123Z",
            Level::Warn,
            "tray restart failed",
        );
        assert!(!line.contains('\n'));
        let parsed: serde_json::Value = serde_json::from_str(&line).expect("valid JSON");
        // The four keys backend/coffer/application/log_reader.py lifts onto
        // its own columns; `warning` is structlog's word, not log's `WARN`.
        assert_eq!(parsed["timestamp"], "2026-09-16T08:12:03.123Z");
        assert_eq!(parsed["level"], "warning");
        assert_eq!(parsed["logger"], "coffer.desktop");
        assert_eq!(parsed["event"], "tray restart failed");
    }

    #[test]
    fn a_message_with_quotes_and_newlines_stays_one_line() {
        // The reason this goes through serde_json: an error string carrying a
        // newline would otherwise split into two records, the second of them
        // unparseable.
        let line = json_line("1970-01-01T00:00:00.000Z", Level::Error, "a \"b\"\nc");
        assert!(!line.contains('\n'));
        let parsed: serde_json::Value = serde_json::from_str(&line).expect("valid JSON");
        assert_eq!(parsed["event"], "a \"b\"\nc");
    }

    #[test]
    fn a_record_reaches_the_sink_as_one_terminated_line() {
        // The half of `Log::log` that is not `open_daemon_log`: what actually
        // gets appended, byte for byte. The trailing newline matters — without
        // it the next writer to this shared file continues this record's line.
        let mut sink: Vec<u8> = Vec::new();
        let t = UNIX_EPOCH + Duration::from_secs(1_789_546_323);
        append_record(&mut sink, t, Level::Info, "daemon restarted (pid 4242)").unwrap();
        append_record(
            &mut sink,
            t,
            Level::Warn,
            "tray.restart_daemon failed: nope",
        )
        .unwrap();

        let written = String::from_utf8(sink).expect("utf-8");
        let lines: Vec<&str> = written.lines().collect();
        assert_eq!(lines.len(), 2, "{written}");
        assert!(written.ends_with('\n'));
        let first: serde_json::Value = serde_json::from_str(lines[0]).expect("valid JSON");
        assert_eq!(first["event"], "daemon restarted (pid 4242)");
        assert_eq!(first["level"], "info");
        assert_eq!(first["timestamp"], "2026-09-16T08:12:03.000Z");
        let second: serde_json::Value = serde_json::from_str(lines[1]).expect("valid JSON");
        assert_eq!(second["level"], "warning");
    }

    #[test]
    fn info_is_logged_and_debug_is_not() {
        // set_max_level is Info, and `enabled` agrees with it — so the two
        // cannot drift into "filtered out but still formatted".
        let logger = FileLogger;
        let at = |level| logger.enabled(&Metadata::builder().level(level).target("coffer").build());
        assert!(at(Level::Error));
        assert!(at(Level::Warn));
        assert!(at(Level::Info));
        assert!(!at(Level::Debug));
        assert!(!at(Level::Trace));
    }
}
