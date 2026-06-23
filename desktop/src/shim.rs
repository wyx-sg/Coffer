//! Sidecar-deploy: copy the bundled `coffer-mcp-shim` AND `coffer-daemon`
//! binaries into a user-writable directory on app startup so they're on the
//! user's PATH after they add `~/.coffer/bin` (macOS/Linux) or the equivalent
//! on Windows. Deploying the daemon next to the shim matters for the frozen
//! auto-spawn path: when an MCP client launches the shim after a reboot (app
//! not running), the shim resolves `coffer-daemon` as its sibling (ADR-006)
//! — a shim-only deploy would leave that probe with nothing to find.
//!
//! Split out of `lib.rs` to keep the top-level entry-point file under the
//! project's 400-line cap (see `agents/stack.md`).

use std::env;
use std::fs;
use std::path::PathBuf;

use tauri::{AppHandle, Manager};

/// Result of a single sidecar-deploy attempt (currently only consumed by
/// tests and logging — the JS `ShimDeployCard` was removed).
#[derive(serde::Serialize)]
pub struct SidecarDeployResult {
    /// Absolute path to the deployed binary on the user's system.
    pub path: String,
    /// `true` if we actually copied (first install or upgrade); `false` if
    /// the target already matched the bundled binary and no copy was needed.
    pub deployed: bool,
}

/// App version baked in at compile time from Cargo.toml. Written into a
/// `.version` sentinel next to the deployed shim so cross-version upgrades
/// (same-size binary) are detected and force a re-copy.
const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Returns the user-writable destination for a deployed sidecar binary
/// named `exe_base` (no `.exe` suffix — appended here on Windows).
///
/// - macOS / Linux: `~/.coffer/bin/<exe_base>`
/// - Windows:       `%LOCALAPPDATA%\coffer\bin\<exe_base>.exe`
pub fn user_bin_path(exe_base: &str) -> PathBuf {
    let exe_name = if cfg!(target_os = "windows") {
        format!("{exe_base}.exe")
    } else {
        exe_base.to_string()
    };

    // Windows lives under %LOCALAPPDATA%\coffer (no leading dot); POSIX uses
    // the conventional dotfile ~/.coffer.
    let (base, coffer_dir): (PathBuf, &str) = if cfg!(target_os = "windows") {
        let base = env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                env::var("USERPROFILE")
                    .map(|h| PathBuf::from(h).join("AppData").join("Local"))
                    .unwrap_or_else(|_| PathBuf::from("."))
            });
        (base, "coffer")
    } else {
        let base = env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."));
        (base, ".coffer")
    };

    base.join(coffer_dir).join("bin").join(exe_name)
}

/// Locate a bundled sidecar binary alongside this application, probing each
/// of `exe_names` in every platform-specific candidate directory.
///
/// Tauri 2 stages `externalBin` differently per platform:
///   * macOS: `Foo.app/Contents/MacOS/<binary>` (next to the main exe).
///   * Linux/Windows AppImage/MSI: alongside the resource directory.
///
/// We probe `Contents/MacOS/` explicitly on macOS, plus the resource dir
/// itself and its parent to cover older layouts and Linux/Windows. On Windows
/// the caller's name(s) plus a `.exe` variant are both tried in each location.
///
/// Shared by `deploy_sidecars_to_user_path` and `daemon::bundled_daemon_path`
/// so the sidecar probes can never diverge again.
pub fn resolve_sidecar(app: &AppHandle, exe_names: &[&str]) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;

    let parent = resource_dir.parent().map(|p| p.to_owned());
    // macOS: Tauri places externalBin in Contents/MacOS/, sibling of
    // Contents/Resources/. resource_dir() returns Contents/Resources, so
    // its parent (Contents) joined with MacOS is where the sidecar lives.
    let macos_dir = parent.as_deref().map(|p| p.join("MacOS"));

    // Each probe directory, in priority order.
    let dirs: Vec<PathBuf> = [
        macos_dir,
        Some(resource_dir.clone()),
        parent,
    ]
    .into_iter()
    .flatten()
    .collect();

    let mut candidates: Vec<PathBuf> = Vec::new();
    for dir in &dirs {
        for name in exe_names {
            candidates.push(dir.join(name));
            // Always also try the Windows `.exe` variant so a probe configured
            // with a bare name still finds the `.exe` on Windows.
            if !name.ends_with(".exe") {
                candidates.push(dir.join(format!("{name}.exe")));
            }
        }
    }

    for c in &candidates {
        if c.is_file() {
            return Ok(c.clone());
        }
    }

    let wanted = exe_names.join(", ");
    Err(format!(
        "{wanted} not found near {} (searched {} candidates)",
        resource_dir.display(),
        candidates.len()
    ))
}

/// Path to the version sentinel that sits next to a deployed sidecar binary
/// named `exe_base` (e.g. `.coffer-mcp-shim.version` for `coffer-mcp-shim`).
pub fn version_sentinel_path(exe_base: &str) -> PathBuf {
    let mut p = user_bin_path(exe_base);
    p.set_file_name(format!(".{exe_base}.version"));
    p
}

/// Decide whether the deployed shim needs to be replaced.
///
/// We treat the deployed binary as stale when ANY of the following differ
/// from the bundled binary:
///   * file size (cheap byte-length proxy for content change)
///   * bundled mtime is newer than deployed mtime (dev/PR builds bump
///     the binary without bumping the version string)
///   * `.version` sentinel content differs from the current `APP_VERSION`
///     (catches the case where two builds happen to produce a same-size
///     binary across versions — pure size-equality would miss it).
///
/// Missing target file or missing sentinel both force a copy.
pub fn shim_needs_copy(target: &PathBuf, bundled: &PathBuf, sentinel: &PathBuf) -> bool {
    let (t_meta, b_meta) = match (fs::metadata(target), fs::metadata(bundled)) {
        (Ok(t), Ok(b)) => (t, b),
        _ => return true,
    };

    if t_meta.len() != b_meta.len() {
        return true;
    }

    // mtime comparison — if either side errors, fall through to other checks.
    if let (Ok(t_mtime), Ok(b_mtime)) = (t_meta.modified(), b_meta.modified()) {
        if b_mtime > t_mtime {
            return true;
        }
    }

    // Version-sentinel comparison.
    match fs::read_to_string(sentinel) {
        Ok(s) => s.trim() != APP_VERSION,
        Err(_) => true,
    }
}

/// Atomically replace `target` with the contents of `bundled`.
///
/// Copies to a sibling temp file in the SAME directory (so the final
/// `rename` is a same-filesystem atomic swap) and only then renames over the
/// target. A crash or a concurrently-executing shim therefore never observes
/// a half-written binary: it sees either the old file or the complete new one
/// — never a truncated one. On Unix the 0o755 mode is set on the temp file
/// before the rename so the swapped-in binary is executable from the instant
/// it appears at `target`.
pub fn atomic_replace(bundled: &PathBuf, target: &PathBuf) -> Result<(), String> {
    let mut tmp = target.clone();
    let fname = target
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_else(|| "coffer-mcp-shim".to_string());
    tmp.set_file_name(format!(".{}.tmp-{}", fname, std::process::id()));

    fs::copy(bundled, &tmp)
        .map_err(|e| format!("copy {} → {}: {e}", bundled.display(), tmp.display()))?;

    // Make the binary executable on Unix BEFORE the rename so the swap exposes
    // an already-runnable file.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = match fs::metadata(&tmp) {
            Ok(m) => m.permissions(),
            Err(e) => {
                let _ = fs::remove_file(&tmp);
                return Err(e.to_string());
            }
        };
        perms.set_mode(0o755);
        if let Err(e) = fs::set_permissions(&tmp, perms) {
            let _ = fs::remove_file(&tmp);
            return Err(e.to_string());
        }
    }

    fs::rename(&tmp, target).map_err(|e| {
        let _ = fs::remove_file(&tmp);
        format!("rename {} → {}: {e}", tmp.display(), target.display())
    })
}

/// Deploy one bundled binary to its user-path `target`: create the parent
/// directory, decide staleness via `shim_needs_copy()` (see its doc-comment
/// for the full rule), copy with `atomic_replace`, and refresh the version
/// `sentinel`. Returns whether a copy actually happened. Split from
/// [`deploy_sidecars_to_user_path`] so the filesystem logic is unit-testable
/// without an `AppHandle`.
pub fn deploy_binary(
    bundled: &PathBuf,
    target: &PathBuf,
    sentinel: &PathBuf,
) -> Result<bool, String> {
    // Ensure destination directory exists.
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
    }

    let needs_copy = shim_needs_copy(target, bundled, sentinel);

    if needs_copy {
        atomic_replace(bundled, target)?;

        // Best-effort: write/refresh the version sentinel. Failure here is
        // not fatal — we'll just re-copy on the next launch.
        let _ = fs::write(sentinel, APP_VERSION);
    }

    Ok(needs_copy)
}

/// Copy the bundled `coffer-mcp-shim`, `coffer-daemon` AND `coffer-hook`
/// binaries into `~/.coffer/bin/` (or the Windows equivalent). The shim is what
/// MCP clients invoke once the directory is on PATH; the co-located daemon is
/// what the frozen shim's detect-or-spawn resolves as its sibling (ADR-006), so
/// auto-spawn works even when the desktop app isn't running; the co-located
/// `coffer-hook` is what the daemon resolves (next to its own executable) when
/// installing an agent's SessionStart rules hook.
pub fn deploy_sidecars_to_user_path(app: AppHandle) -> Result<Vec<SidecarDeployResult>, String> {
    let mut results = Vec::new();
    for name in ["coffer-mcp-shim", "coffer-daemon", "coffer-hook"] {
        let bundled = resolve_sidecar(&app, &[name])?;
        let target = user_bin_path(name);
        let deployed = deploy_binary(&bundled, &target, &version_sentinel_path(name))?;
        results.push(SidecarDeployResult {
            path: target.to_string_lossy().into_owned(),
            deployed,
        });
    }
    Ok(results)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};
    use std::time::Duration;

    static COUNTER: AtomicU32 = AtomicU32::new(0);

    /// A unique throwaway directory under the system temp dir, removed on drop.
    /// (Avoids adding the `tempfile` dev-dependency for a handful of tests.)
    struct TmpDir(PathBuf);

    impl TmpDir {
        fn new() -> Self {
            let n = COUNTER.fetch_add(1, Ordering::SeqCst);
            let p = env::temp_dir().join(format!("coffer_shim_test_{}_{}", std::process::id(), n));
            fs::create_dir_all(&p).expect("create temp dir");
            TmpDir(p)
        }
        fn path(&self, name: &str) -> PathBuf {
            self.0.join(name)
        }
    }

    impl Drop for TmpDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn write(p: &PathBuf, contents: &str) {
        fs::write(p, contents).expect("write temp file");
    }

    /// Re-write `newer` until its mtime strictly exceeds `older`'s, so the
    /// mtime-comparison branch is exercised deterministically regardless of the
    /// filesystem's timestamp resolution.
    fn make_strictly_newer(newer: &PathBuf, older: &PathBuf, contents: &str) {
        for _ in 0..200 {
            write(newer, contents);
            let n = fs::metadata(newer).unwrap().modified().unwrap();
            let o = fs::metadata(older).unwrap().modified().unwrap();
            if n > o {
                return;
            }
            std::thread::sleep(Duration::from_millis(2));
        }
        panic!("could not make {newer:?} newer than {older:?}");
    }

    #[test]
    fn needs_copy_when_target_missing() {
        let d = TmpDir::new();
        let (target, bundled, sentinel) = (d.path("shim"), d.path("bundled"), d.path(".version"));
        write(&bundled, "BINARY");
        assert!(shim_needs_copy(&target, &bundled, &sentinel));
    }

    #[test]
    fn needs_copy_when_size_differs() {
        let d = TmpDir::new();
        let (target, bundled, sentinel) = (d.path("shim"), d.path("bundled"), d.path(".version"));
        write(&target, "SHORT");
        write(&bundled, "MUCH-LONGER-BINARY");
        write(&sentinel, APP_VERSION);
        assert!(shim_needs_copy(&target, &bundled, &sentinel));
    }

    #[test]
    fn needs_copy_when_bundled_newer() {
        let d = TmpDir::new();
        let (target, bundled, sentinel) = (d.path("shim"), d.path("bundled"), d.path(".version"));
        write(&target, "BINARY");
        make_strictly_newer(&bundled, &target, "BINARY"); // same size, bundled newer
        write(&sentinel, APP_VERSION); // version matches → only the mtime triggers
        assert!(shim_needs_copy(&target, &bundled, &sentinel));
    }

    #[test]
    fn needs_copy_when_sentinel_missing() {
        let d = TmpDir::new();
        let (target, bundled, sentinel) = (d.path("shim"), d.path("bundled"), d.path(".version"));
        write(&bundled, "BINARY");
        make_strictly_newer(&target, &bundled, "BINARY"); // bundled not newer
        assert!(shim_needs_copy(&target, &bundled, &sentinel)); // sentinel absent
    }

    #[test]
    fn needs_copy_when_sentinel_version_differs() {
        let d = TmpDir::new();
        let (target, bundled, sentinel) = (d.path("shim"), d.path("bundled"), d.path(".version"));
        write(&bundled, "BINARY");
        make_strictly_newer(&target, &bundled, "BINARY");
        write(&sentinel, "0.0.0-stale");
        assert!(shim_needs_copy(&target, &bundled, &sentinel));
    }

    #[test]
    #[cfg(not(target_os = "windows"))]
    fn shim_user_path_uses_dot_coffer_on_posix() {
        let p = user_bin_path("coffer-mcp-shim");
        let s = p.to_string_lossy();
        assert!(s.contains("/.coffer/bin/"), "POSIX path should use ~/.coffer/bin: {s}");
        assert!(s.ends_with("coffer-mcp-shim"), "POSIX exe name: {s}");
    }

    #[test]
    #[cfg(target_os = "windows")]
    fn shim_user_path_uses_no_dot_coffer_on_windows() {
        let p = user_bin_path("coffer-mcp-shim");
        let s = p.to_string_lossy();
        assert!(s.contains(r"\coffer\bin\"), "Windows path should use coffer (no dot): {s}");
        assert!(!s.contains(r"\.coffer\"), "Windows path must not contain .coffer: {s}");
        assert!(s.ends_with("coffer-mcp-shim.exe"), "Windows exe name: {s}");
    }

    #[test]
    fn daemon_user_path_sits_in_same_bin_dir_as_shim() {
        let daemon = user_bin_path("coffer-daemon");
        let shim = user_bin_path("coffer-mcp-shim");
        assert_eq!(daemon.parent(), shim.parent(), "both binaries share ~/.coffer/bin");
        let expected = if cfg!(target_os = "windows") {
            "coffer-daemon.exe"
        } else {
            "coffer-daemon"
        };
        assert_eq!(daemon.file_name().unwrap().to_string_lossy(), expected);
    }

    #[test]
    fn daemon_sentinel_sits_next_to_daemon() {
        let daemon = user_bin_path("coffer-daemon");
        let sentinel = version_sentinel_path("coffer-daemon");
        assert_eq!(daemon.parent(), sentinel.parent(), "sentinel must be in same dir as daemon");
        assert_eq!(
            sentinel.file_name().unwrap().to_string_lossy(),
            ".coffer-daemon.version"
        );
    }

    #[test]
    fn deploy_binary_copies_creates_dir_and_writes_sentinel() {
        let d = TmpDir::new();
        let bundled = d.path("bundled");
        write(&bundled, "DAEMON-BINARY");
        // Nested target exercises the create_dir_all branch.
        let target = d.path("bin").join("coffer-daemon");
        let sentinel = d.path("bin").join(".coffer-daemon.version");

        let deployed = deploy_binary(&bundled, &target, &sentinel).expect("deploy");

        assert!(deployed, "first deploy must copy");
        assert_eq!(fs::read_to_string(&target).unwrap(), "DAEMON-BINARY");
        assert_eq!(fs::read_to_string(&sentinel).unwrap().trim(), APP_VERSION);
    }

    #[test]
    fn deploy_binary_is_idempotent_when_current() {
        let d = TmpDir::new();
        let bundled = d.path("bundled");
        write(&bundled, "DAEMON-BINARY");
        let target = d.path("coffer-daemon");
        let sentinel = d.path(".coffer-daemon.version");

        assert!(deploy_binary(&bundled, &target, &sentinel).expect("first deploy"));
        let second = deploy_binary(&bundled, &target, &sentinel).expect("second deploy");

        assert!(!second, "matching size + version + mtime must skip the copy");
    }

    #[test]
    fn deploy_binary_redeploys_on_version_drift() {
        let d = TmpDir::new();
        let bundled = d.path("bundled");
        write(&bundled, "DAEMON-BINARY");
        let target = d.path("coffer-daemon");
        let sentinel = d.path(".coffer-daemon.version");

        assert!(deploy_binary(&bundled, &target, &sentinel).expect("first deploy"));
        write(&sentinel, "0.0.0-stale");

        let redeployed = deploy_binary(&bundled, &target, &sentinel).expect("redeploy");
        assert!(redeployed, "a stale version sentinel must force a re-copy");
        assert_eq!(fs::read_to_string(&sentinel).unwrap().trim(), APP_VERSION);
    }

    #[test]
    fn sentinel_path_sits_next_to_shim() {
        let shim = user_bin_path("coffer-mcp-shim");
        let sentinel = version_sentinel_path("coffer-mcp-shim");
        assert_eq!(shim.parent(), sentinel.parent(), "sentinel must be in same dir as shim");
        assert_eq!(
            sentinel.file_name().unwrap().to_string_lossy(),
            ".coffer-mcp-shim.version"
        );
    }

    #[test]
    fn no_copy_when_size_version_match_and_not_newer() {
        let d = TmpDir::new();
        let (target, bundled, sentinel) = (d.path("shim"), d.path("bundled"), d.path(".version"));
        write(&bundled, "BINARY");
        make_strictly_newer(&target, &bundled, "BINARY"); // target newer → bundled not newer
        write(&sentinel, APP_VERSION);
        assert!(!shim_needs_copy(&target, &bundled, &sentinel));
    }

    #[test]
    fn atomic_replace_writes_full_content_and_leaves_no_temp() {
        let d = TmpDir::new();
        let (target, bundled) = (d.path("shim"), d.path("bundled"));
        write(&bundled, "NEW-BINARY-CONTENT");
        atomic_replace(&bundled, &target).expect("atomic replace");
        assert_eq!(fs::read_to_string(&target).unwrap(), "NEW-BINARY-CONTENT");
        // No leftover temp sibling.
        let leftovers: Vec<_> = fs::read_dir(&d.0)
            .unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .filter(|n| n.contains(".tmp-"))
            .collect();
        assert!(leftovers.is_empty(), "temp files left behind: {leftovers:?}");
    }

    #[test]
    fn atomic_replace_overwrites_existing_target() {
        let d = TmpDir::new();
        let (target, bundled) = (d.path("shim"), d.path("bundled"));
        write(&target, "OLD");
        write(&bundled, "REPLACEMENT");
        atomic_replace(&bundled, &target).expect("atomic replace");
        assert_eq!(fs::read_to_string(&target).unwrap(), "REPLACEMENT");
    }

    #[test]
    #[cfg(unix)]
    fn atomic_replace_sets_executable_bit_on_unix() {
        use std::os::unix::fs::PermissionsExt;
        let d = TmpDir::new();
        let (target, bundled) = (d.path("shim"), d.path("bundled"));
        write(&bundled, "BINARY");
        atomic_replace(&bundled, &target).expect("atomic replace");
        let mode = fs::metadata(&target).unwrap().permissions().mode();
        assert_eq!(mode & 0o111, 0o111, "replaced binary must be executable");
    }
}
