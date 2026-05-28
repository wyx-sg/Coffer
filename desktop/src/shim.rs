//! Shim-deploy: copy the bundled `coffer-mcp-shim` sidecar binary into a
//! user-writable directory on app startup so it's on the user's PATH after
//! they add `~/.coffer/bin` (macOS/Linux) or the equivalent on Windows.
//!
//! Split out of `lib.rs` to keep the top-level entry-point file under the
//! project's 400-line cap (see `agents/stack.md`).

use std::env;
use std::fs;
use std::path::PathBuf;

use tauri::{AppHandle, Manager};

/// Result of a single shim-deploy attempt, returned to the JS layer when
/// the relevant Tauri command is invoked (currently only consumed by tests
/// and logging — the JS `ShimDeployCard` was removed).
#[derive(serde::Serialize)]
pub struct ShimDeployResult {
    /// Absolute path to the deployed shim binary on the user's system.
    pub path: String,
    /// `true` if we actually copied (first install or upgrade); `false` if
    /// the target already matched the bundled binary and no copy was needed.
    pub deployed: bool,
}

/// App version baked in at compile time from Cargo.toml. Written into a
/// `.version` sentinel next to the deployed shim so cross-version upgrades
/// (same-size binary) are detected and force a re-copy.
const APP_VERSION: &str = env!("CARGO_PKG_VERSION");

/// Returns the user-writable destination for the MCP shim binary.
///
/// - macOS / Linux: `~/.coffer/bin/coffer-mcp-shim`
/// - Windows:       `%LOCALAPPDATA%\coffer\bin\coffer-mcp-shim.exe`
pub fn shim_user_path() -> PathBuf {
    let exe_name = if cfg!(target_os = "windows") {
        "coffer-mcp-shim.exe"
    } else {
        "coffer-mcp-shim"
    };

    let base: PathBuf = if cfg!(target_os = "windows") {
        env::var("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| {
                env::var("USERPROFILE")
                    .map(|h| PathBuf::from(h).join("AppData").join("Local"))
                    .unwrap_or_else(|_| PathBuf::from("."))
            })
    } else {
        env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
    };

    base.join(".coffer").join("bin").join(exe_name)
}

/// Locate the `coffer-mcp-shim` sidecar that was bundled alongside this
/// application.
///
/// Tauri 2 stages `externalBin` differently per platform:
///   * macOS: `Foo.app/Contents/MacOS/<binary>` (next to the main exe).
///   * Linux/Windows AppImage/MSI: alongside the resource directory.
///
/// We probe `Contents/MacOS/` explicitly on macOS, plus the resource dir
/// itself and its parent to cover older layouts and Linux/Windows.
pub fn bundled_shim_path(app: &AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;

    let parent = resource_dir.parent().map(|p| p.to_owned());
    // macOS: Tauri places externalBin in Contents/MacOS/, sibling of
    // Contents/Resources/. resource_dir() returns Contents/Resources, so
    // its parent (Contents) joined with MacOS is where the sidecar lives.
    let macos_dir = parent.as_deref().map(|p| p.join("MacOS"));

    let candidates: Vec<PathBuf> = [
        macos_dir.as_deref().map(|p| p.join("coffer-mcp-shim")),
        Some(resource_dir.join("coffer-mcp-shim")),
        Some(resource_dir.join("coffer-mcp-shim.exe")),
        parent.as_deref().map(|p| p.join("coffer-mcp-shim")),
        parent.as_deref().map(|p| p.join("coffer-mcp-shim.exe")),
    ]
    .into_iter()
    .flatten()
    .collect();

    for c in &candidates {
        if c.is_file() {
            return Ok(c.clone());
        }
    }

    Err(format!(
        "coffer-mcp-shim not found in {} (searched {} candidates)",
        resource_dir.display(),
        candidates.len()
    ))
}

/// Path to the version sentinel that sits next to the deployed shim.
pub fn shim_version_sentinel_path() -> PathBuf {
    let mut p = shim_user_path();
    p.set_file_name(".coffer-mcp-shim.version");
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

/// Copy the bundled `coffer-mcp-shim` binary into `~/.coffer/bin/` (or the
/// Windows equivalent), making it available on the user's PATH once they
/// add that directory.  Staleness is decided by `shim_needs_copy()` — see
/// its doc-comment for the full rule.
pub fn deploy_shim_to_user_path(app: AppHandle) -> Result<ShimDeployResult, String> {
    let bundled = bundled_shim_path(&app)?;
    let target = shim_user_path();
    let sentinel = shim_version_sentinel_path();

    // Ensure destination directory exists.
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
    }

    let needs_copy = shim_needs_copy(&target, &bundled, &sentinel);

    if needs_copy {
        fs::copy(&bundled, &target)
            .map_err(|e| format!("copy {} → {}: {e}", bundled.display(), target.display()))?;

        // Make the binary executable on Unix platforms.
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(&target)
                .map_err(|e| e.to_string())?
                .permissions();
            perms.set_mode(0o755);
            fs::set_permissions(&target, perms).map_err(|e| e.to_string())?;
        }

        // Best-effort: write/refresh the version sentinel. Failure here is
        // not fatal — we'll just re-copy on the next launch.
        let _ = fs::write(&sentinel, APP_VERSION);
    }

    Ok(ShimDeployResult {
        path: target.to_string_lossy().into_owned(),
        deployed: needs_copy,
    })
}
