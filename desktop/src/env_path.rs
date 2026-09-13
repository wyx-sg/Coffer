//! The `$PATH` the shell hands a daemon it spawns, and the login-shell probe
//! that discovers it.
//!
//! A Finder/Dock-launched `.app` inherits the minimal GUI PATH
//! (`/usr/bin:/bin:/usr/sbin:/sbin`), so a daemon spawned from it — and the
//! `npx`/`uvx` MCP upstreams that daemon spawns in turn — would fail ENOENT.
//! We ask the user's login shell for its real `$PATH` and merge it back in.
//!
//! Split out of `spawn.rs` to keep every file under the project's 400-line
//! cap (see `agents/stack.md`).

use std::env;
use std::path::PathBuf;

/// Sentinel wrapped around `$PATH` in the login-shell probe output so the
/// value survives any chatter a user's shell profile prints to stdout.
#[cfg(unix)]
const PATH_PROBE_MARKER: &str = "__COFFER_PATH__";

/// Extract the marker-delimited `$PATH` value from login-shell probe output.
/// Returns `None` when the markers are missing/unpaired or the value is empty
/// — callers treat that as "probe failed" and fall back.
#[cfg(unix)]
fn extract_marked_path(output: &str) -> Option<String> {
    let start = output.find(PATH_PROBE_MARKER)? + PATH_PROBE_MARKER.len();
    let end = output[start..].find(PATH_PROBE_MARKER)? + start;
    let path = output[start..end].trim();
    if path.is_empty() {
        None
    } else {
        Some(path.to_string())
    }
}

/// Ask the user's login shell for its `$PATH` (`$SHELL -lc`, so Homebrew /
/// nvm / pyenv exports in `~/.zprofile` etc. apply). Polls `try_wait` up to
/// `timeout` and kills the child on expiry rather than blocking the caller
/// on a hung profile. Returns `None` on any failure — callers fall back.
#[cfg(unix)]
fn login_shell_path(timeout: std::time::Duration) -> Option<String> {
    use std::io::Read;
    use std::process::{Command, Stdio};
    use std::time::Instant;

    let shell = env::var("SHELL").unwrap_or_else(|_| "/bin/sh".to_string());
    let probe = format!(
        "printf '%s%s%s' '{m}' \"$PATH\" '{m}'",
        m = PATH_PROBE_MARKER
    );
    let mut child = Command::new(&shell)
        .args(["-lc", &probe])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;

    let deadline = Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => break,
            Ok(Some(_)) => return None,
            Ok(None) if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
            Ok(None) => std::thread::sleep(std::time::Duration::from_millis(50)),
            Err(_) => return None,
        }
    }

    let mut out = String::new();
    child.stdout.take()?.read_to_string(&mut out).ok()?;
    extract_marked_path(&out)
}

/// Merge PATH sources for the daemon spawn, preserving order and deduping:
/// login-shell entries first, then the current process's entries, then
/// well-known tool dirs (Homebrew, `/usr/local/bin`, `~/.local/bin`,
/// `~/.cargo/bin`) as a safety net for when the login-shell probe fails.
/// Pure so it's unit-testable; empty segments are skipped.
#[cfg(unix)]
fn merged_spawn_path(
    login_path: Option<&str>,
    current_path: Option<&str>,
    home: Option<&str>,
) -> String {
    fn push_unique(entries: &mut Vec<String>, dir: &str) {
        if !dir.is_empty() && !entries.iter().any(|e| e == dir) {
            entries.push(dir.to_string());
        }
    }

    let mut entries: Vec<String> = Vec::new();
    for source in [login_path, current_path].into_iter().flatten() {
        for dir in source.split(':') {
            push_unique(&mut entries, dir);
        }
    }
    for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
        push_unique(&mut entries, dir);
    }
    if let Some(home) = home {
        for sub in [".local/bin", ".cargo/bin"] {
            push_unique(&mut entries, &format!("{home}/{sub}"));
        }
    }
    entries.join(":")
}

/// The PATH the spawned daemon should run with. The login-shell probe is
/// cached for the app's lifetime (`OnceLock`) — it costs a shell startup, and
/// the login PATH doesn't change while the app runs.
///
/// Also the PATH that step 4 of the daemon-resolution chain searches, so
/// "on `$PATH`" means the same thing whether we are looking a binary up or
/// handing the environment to one we spawn.
#[cfg(unix)]
pub fn daemon_spawn_path() -> String {
    static LOGIN_PATH: std::sync::OnceLock<Option<String>> = std::sync::OnceLock::new();
    let login = LOGIN_PATH.get_or_init(|| login_shell_path(std::time::Duration::from_secs(3)));
    merged_spawn_path(
        login.as_deref(),
        env::var("PATH").ok().as_deref(),
        env::var("HOME").ok().as_deref(),
    )
}

/// Windows has no login-shell notion to probe — a GUI-launched process already
/// inherits the user's `PATH` from the registry environment.
#[cfg(not(unix))]
pub fn daemon_spawn_path() -> String {
    env::var("PATH").unwrap_or_default()
}

/// Every `<dir>/<exe_name>` a `PATH`-style variable names, in order. Pure so
/// the lookup order is unit-testable without touching the filesystem; the
/// caller filters for the first entry that actually exists.
pub fn path_candidates(path_var: &str, exe_name: &str) -> Vec<PathBuf> {
    env::split_paths(path_var)
        .filter(|p| !p.as_os_str().is_empty())
        .map(|p| p.join(exe_name))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- daemon-spawn PATH: a Finder/Dock-launched .app inherits the minimal
    // GUI PATH, so the daemon (and its npx/uvx MCP upstreams) needs the user's
    // login-shell PATH merged back in before spawn. ---

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_puts_login_shell_entries_first() {
        let merged = merged_spawn_path(
            Some("/opt/homebrew/bin:/usr/bin"),
            Some("/usr/bin:/bin"),
            None,
        );
        assert_eq!(merged, "/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin");
    }

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_without_login_shell_appends_well_known_dirs() {
        let merged = merged_spawn_path(None, Some("/usr/bin:/bin"), Some("/Users/u"));
        assert_eq!(
            merged,
            "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin:/Users/u/.local/bin:/Users/u/.cargo/bin"
        );
    }

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_dedupes_keeping_first_occurrence() {
        let merged = merged_spawn_path(
            Some("/usr/local/bin:/usr/bin"),
            Some("/usr/bin:/usr/local/bin:/bin"),
            None,
        );
        assert_eq!(merged, "/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin");
    }

    #[cfg(unix)]
    #[test]
    fn merged_spawn_path_skips_empty_segments() {
        let merged = merged_spawn_path(Some(":/usr/bin::"), None, None);
        assert_eq!(merged, "/usr/bin:/opt/homebrew/bin:/usr/local/bin");
    }

    #[cfg(unix)]
    #[test]
    fn extract_marked_path_ignores_profile_chatter() {
        let out = format!(
            "welcome banner\n{m}/a:/b{m}\ntrailing",
            m = PATH_PROBE_MARKER
        );
        assert_eq!(extract_marked_path(&out).as_deref(), Some("/a:/b"));
    }

    #[cfg(unix)]
    #[test]
    fn extract_marked_path_missing_or_unpaired_markers_is_none() {
        assert_eq!(extract_marked_path("/usr/bin:/bin"), None);
        assert_eq!(
            extract_marked_path(&format!("{PATH_PROBE_MARKER}/usr/bin")),
            None
        );
    }

    #[cfg(unix)]
    #[test]
    fn extract_marked_path_empty_value_is_none() {
        assert_eq!(
            extract_marked_path(&format!("{m}  {m}", m = PATH_PROBE_MARKER)),
            None
        );
    }

    #[cfg(unix)]
    #[test]
    fn path_candidates_preserves_order_and_skips_empty_segments() {
        let found = path_candidates("/a::/b", "coffer-daemon");
        assert_eq!(
            found,
            vec![
                PathBuf::from("/a/coffer-daemon"),
                PathBuf::from("/b/coffer-daemon"),
            ]
        );
    }

    #[test]
    fn path_candidates_of_empty_var_is_empty() {
        assert!(path_candidates("", "coffer-daemon").is_empty());
    }
}
