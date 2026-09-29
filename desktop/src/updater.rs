//! Checking for, downloading and installing a new version of the app (spec
//! desktop-app "Check for updates against a signed release manifest").
//!
//! Everything runs here, in the shell's own process: the manifest is fetched
//! and the archive verified by `tauri-plugin-updater` in Rust, so the webview's
//! content policy stays loopback and IPC only and the page is granted none of
//! the plugin's permissions. The page asks through four commands and hears
//! back through one event; the menu bar is relabelled from the same record.
//!
//! The manifest is `latest.json` on the newest GitHub Release (the endpoint in
//! `tauri.conf.json`), written and signed by the release workflow. The public
//! key it is verified against is built in at compile time from
//! `COFFER_UPDATER_PUBKEY`; a build without one — every build from source —
//! reports itself unconfigured and never checks.
//!
//! A check never installs. Only the user's own Download and restart (the About
//! tab, or the menu bar's "Restart to install") downloads the archive, verifies
//! its signature, replaces the `.app` and relaunches. The relaunched shell then
//! replaces the previous version's daemon through the one restart path
//! (`daemon.rs`, `RELAUNCHED_FOR_UPDATE`).

use std::sync::Mutex;
use std::time::{Duration, SystemTime};

use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_updater::{Error as UpdaterError, Update, UpdaterExt};

use crate::daemon::APP_VERSION;
use crate::update_state::{
    check_due, epoch_ms, AvailableUpdate, Failure, UpdateStatus, CHECK_TIMEOUT, FIRST_CHECK_DELAY,
};

/// The updater public key this build verifies archives against: the contents
/// of the `.key.pub` file `tauri signer generate` wrote, set by the release
/// workflow from the `COFFER_UPDATER_PUBKEY` repository variable.
pub const UPDATER_PUBKEY: Option<&str> = option_env!("COFFER_UPDATER_PUBKEY");

/// The event every status change is announced on; the About tab listens.
pub const UPDATE_EVENT: &str = "coffer://update";

/// Set on the process before it relaunches onto a new version, and inherited
/// by the relaunched one, which reads it to know the daemon it finds is the
/// previous version's (`daemon.rs`).
pub const RELAUNCHED_FOR_UPDATE: &str = "COFFER_RELAUNCHED_FOR_UPDATE";

/// How often the schedule thread wakes to ask [`check_due`].
const SCHEDULE_TICK: Duration = Duration::from_secs(60);
/// A download is one large request; the check's ten seconds would cut it off.
const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(15 * 60);

/// The updater's state, managed by the app.
pub struct Updates {
    status: Mutex<UpdateStatus>,
    /// The update the last successful check found, kept so Download and
    /// restart installs exactly what the user was shown.
    pending: Mutex<Option<Update>>,
    last_attempt: Mutex<Option<SystemTime>>,
}

/// The plugin, with this build's public key. Registered in every build — a
/// build without a key simply never calls it.
pub fn plugin() -> tauri::plugin::TauriPlugin<tauri::Wry, tauri_plugin_updater::Config> {
    let mut builder = tauri_plugin_updater::Builder::new();
    if let Some(key) = UPDATER_PUBKEY {
        builder = builder.pubkey(key);
    }
    builder.build()
}

/// Manage the state and start the launch-then-every-six-hours schedule.
pub fn start(app: &AppHandle) {
    app.manage(Updates {
        status: Mutex::new(UpdateStatus::new(APP_VERSION, UPDATER_PUBKEY.is_some())),
        pending: Mutex::new(None),
        last_attempt: Mutex::new(None),
    });
    if UPDATER_PUBKEY.is_none() {
        log::info!("updater: no update key in this build; not checking for updates");
        return;
    }
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(FIRST_CHECK_DELAY);
        loop {
            let (auto, last) = {
                let u = app.state::<Updates>();
                let auto = lock(&u.status).auto_check;
                let last = *lock(&u.last_attempt);
                (auto, last)
            };
            if check_due(auto, last, SystemTime::now()) {
                let _ = tauri::async_runtime::block_on(run_check(&app));
            }
            std::thread::sleep(SCHEDULE_TICK);
        }
    });
}

fn lock<T>(m: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|e| e.into_inner())
}

/// The current record.
pub fn status(app: &AppHandle) -> UpdateStatus {
    lock(&app.state::<Updates>().status).clone()
}

/// Change the record without telling anyone.
fn record(app: &AppHandle, change: impl FnOnce(&mut UpdateStatus)) -> UpdateStatus {
    let updates = app.state::<Updates>();
    let mut status = lock(&updates.status);
    change(&mut status);
    status.clone()
}

/// Tell the page and the menu bar what the record now says.
fn announce(app: &AppHandle, snapshot: &UpdateStatus) {
    let _ = app.emit(UPDATE_EVENT, snapshot);
    crate::tray::set_update(app, snapshot.clone());
}

/// Change the record, then tell the page and the menu bar.
fn publish(app: &AppHandle, change: impl FnOnce(&mut UpdateStatus)) -> UpdateStatus {
    let snapshot = record(app, change);
    announce(app, &snapshot);
    snapshot
}

/// Whole percent downloaded, for announcing progress once per step rather
/// than once per network chunk.
fn percent(status: &UpdateStatus) -> Option<u64> {
    match (status.downloaded, status.total) {
        (Some(done), Some(total)) if total > 0 => Some(done * 100 / total),
        _ => None,
    }
}

/// Ask the manifest once. Records the attempt, the result and — on failure —
/// a line in the daemon log.
pub async fn run_check(app: &AppHandle) -> Result<UpdateStatus, String> {
    let mut began = Ok(());
    publish(app, |s| began = s.begin_check());
    began?;
    *lock(&app.state::<Updates>().last_attempt) = Some(SystemTime::now());

    let found = check_manifest(app).await;
    let now = epoch_ms(SystemTime::now());
    let result = match found {
        Ok(Some(update)) => {
            log::info!("updater: {} is available", update.version);
            let offer = AvailableUpdate {
                version: update.version.clone(),
                notes: update.body.clone(),
                date: update
                    .raw_json
                    .get("pub_date")
                    .and_then(|d| d.as_str())
                    .map(str::to_owned),
            };
            *lock(&app.state::<Updates>().pending) = Some(update);
            Ok(Some(offer))
        }
        Ok(None) => {
            *lock(&app.state::<Updates>().pending) = None;
            Ok(None)
        }
        Err(failure) => {
            log::warn!("updater: check failed: {}", failure.message());
            Err(failure)
        }
    };
    Ok(publish(app, |s| s.finish_check(now, result)))
}

async fn check_manifest(app: &AppHandle) -> Result<Option<Update>, Failure> {
    let updater = app
        .updater_builder()
        .timeout(CHECK_TIMEOUT)
        .build()
        .map_err(classify)?;
    updater.check().await.map_err(classify)
}

/// Put a plugin error in the About tab's terms.
fn classify(e: UpdaterError) -> Failure {
    let detail = e.to_string();
    match e {
        UpdaterError::Minisign(_)
        | UpdaterError::Base64(_)
        | UpdaterError::SignatureUtf8(_)
        | UpdaterError::SignedVersionMismatch { .. }
        | UpdaterError::MissingSignedVersion => Failure::Signature(detail),
        UpdaterError::Reqwest(_) | UpdaterError::Network(_) => Failure::Network(detail),
        _ => Failure::Other(detail),
    }
}

/// Download, verify and install the update the last check found, then
/// relaunch. Only returns on failure.
pub async fn run_install(app: &AppHandle) -> Result<(), String> {
    let mut began = Ok(());
    publish(app, |s| began = s.begin_install());
    began?;
    let Some(mut update) = lock(&app.state::<Updates>().pending).clone() else {
        let failure = Failure::Other("The update is no longer on offer; check again.".into());
        let message = failure.message();
        publish(app, |s| s.install_failed(failure));
        return Err(message);
    };
    update.timeout = Some(DOWNLOAD_TIMEOUT);
    let version = update.version.clone();
    log::info!("updater: downloading {version}");

    let progress = app.clone();
    let installing = app.clone();
    let mut shown: Option<u64> = None;
    let outcome = update
        .download_and_install(
            move |chunk, total| {
                let snapshot = record(&progress, |s| s.progress(chunk, total));
                let now = percent(&snapshot);
                if now != shown {
                    shown = now;
                    announce(&progress, &snapshot);
                }
            },
            move || {
                publish(&installing, |s| s.installing());
            },
        )
        .await;
    match outcome {
        Ok(()) => {
            log::info!("updater: installed {version}; relaunching");
            // Inherited by the relaunched process (`tauri::process::restart`
            // spawns it directly), which replaces this version's daemon.
            std::env::set_var(RELAUNCHED_FOR_UPDATE, APP_VERSION);
            app.restart();
        }
        Err(e) => {
            let failure = classify(e);
            let message = failure.message();
            log::warn!("updater: install of {version} failed: {message}");
            publish(app, |s| s.install_failed(failure));
            Err(message)
        }
    }
}

// ---------------------------------------------------------------------------
// IPC — reached from the page through `frontend/src/lib/shellUpdates.ts`.
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn update_status(app: AppHandle) -> UpdateStatus {
    status(&app)
}

#[tauri::command]
pub async fn check_for_updates(app: AppHandle) -> Result<UpdateStatus, String> {
    run_check(&app).await
}

#[tauri::command]
pub async fn install_update(app: AppHandle) -> Result<(), String> {
    run_install(&app).await
}

/// The page's "Check automatically" switch. The choice lives in the page's
/// storage, like the interface language, and is reported on every launch.
#[tauri::command]
pub fn set_update_auto_check(app: AppHandle, enabled: bool) -> UpdateStatus {
    publish(&app, |s| s.auto_check = enabled)
}
