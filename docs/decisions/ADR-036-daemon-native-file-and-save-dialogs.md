# ADR-036 — Daemon Native File & Save Dialogs Extend the Picker

> 中文版: [ADR-036-daemon-native-file-and-save-dialogs.zh.md](./ADR-036-daemon-native-file-and-save-dialogs.zh.md)

- **Status:** Accepted
- **Date:** 2026-06-21
- **Deciders:** Yuxing Wu
- **Spec:** [004-agent-registry](../../specs/004-agent-registry/spec.md) owns the `/fs`
  router and gains the file/save picker FRs; [010-sync](../../specs/010-sync/spec.md)
  consumes them for out-of-band master-key transfer. No new spec number; the
  `spec.md` files are updated before implementation.
- **Supersedes:** the "Picking keeps its dual path — deliberately / we do not
  collapse the picker onto the daemon" stance in [ADR-033](./ADR-033-daemon-proxies-os-file-actions.md)
  §4. That stance was already overtaken by the `POST /fs/pick-folder` daemon
  endpoint shipped after ADR-033; this ADR makes the new direction explicit and
  extends it from folders to files.

## Context

ADR-033 routed OS file *actions* (open / reveal) through the loopback daemon so
the web surface matches the desktop app, but §4 deliberately kept *picking* on a
dual path: the OS-native directory dialog on desktop, the in-app daemon folder
browser on the web. A later change (`POST /fs/pick-folder`, `FsPickService`)
already broke that stance for folders — on the web the daemon now opens the host's
**native** directory dialog (`osascript` on macOS, `zenity`/`kdialog` on Linux)
and only falls back to the in-app browser when no native dialog tool exists.

One gap remains: there is **no native FILE-open or SAVE dialog**, only
folder-open. Every place that needs a *file* path therefore either hand-rolls a
desktop-only Tauri dialog or forces the user to type an absolute path into a text
field. The most visible offender is the out-of-band master-key card (spec 010):
on the web it shows a raw `/path/to/coffer-master.key` input and the import/export
buttons act on whatever the user typed. Typing absolute paths is exactly the
friction the folder picker was introduced to remove.

## Decision

**Extend the daemon picker from folders to files: add native open-file and
save-file dialogs, reached the same way as the folder picker.**

### 1. Two new daemon endpoints (spec 004)

`FsPickService` gains two siblings of `pick_folder`, under the same loopback +
token guard, each run in `asyncio.to_thread` because the dialog is modal:

- `POST /api/v1/fs/pick-file` `{ start? }` — open the host's native **open-file**
  dialog and return the chosen absolute file path.
- `POST /api/v1/fs/save-file` `{ suggested_name?, start? }` — open the host's
  native **save-file** dialog (with a suggested file name) and return the chosen
  destination path.

Both reuse the existing three-outcome contract, returned as `{ available, path }`:

- `available=false` — this host has no native dialog tool (Windows has no
  argv-only dialog; Linux without `zenity`/`kdialog`). The caller falls back to a
  typed path.
- `available=true, path=null` — the dialog opened and the user cancelled.
- `available=true, path="…"` — the user chose a path.

Mechanism, mirroring `pick_folder`: macOS `osascript` (`choose file` /
`choose file name`), Linux `zenity --file-selection [--save --confirm-overwrite]`
then `kdialog --getopenfilename` / `--getsavefilename`. The dialog is always
invoked with an **argument vector** (never a shell string); on macOS the start
dir and suggested name are escaped into the AppleScript string literals.

### 2. A shared front-end file-picker helper

`lib/filePicker.ts` exposes `pickOpenFile(start?)` and
`pickSaveFile(suggestedName, start?)`, each returning `{ path, unavailable }`.
Desktop uses the Tauri `open`/`save` dialog; the web uses the new daemon
endpoints; `unavailable` is true only when the daemon reports no native tool (or
the call errors), so the caller can reveal a typed-path fallback.

### 3. Picking is fully native-first; typing is a last resort

The web master-key card no longer shows a path field by default. Import opens the
native open-file dialog; export opens the native save-file dialog. The typed
`keyPath` field appears **only** after a pick reports `unavailable` — on macOS it
never appears. The three existing folder-paired text inputs (skill import, agent
`config_dir` ×2) drop their co-located raw text box for a read-only display of the
picked path plus the `FolderPicker` button (whose own web fallback is the in-app
browser, never typing).

## Consequences

- The web surface picks files the same way it already picks folders; the desktop
  Tauri path is unchanged. Manual path typing survives only as a degraded
  fallback on hosts with no native dialog.
- New OS-surface on the daemon is small and bounded: the dialogs only *return* a
  path the user selected — they create and open nothing. Same trust level as the
  existing `pick-folder` / `browse` routes (loopback + token + argument-vector
  shell-out).
- ADR-033 §4's "dual path, deliberately" is retired. The picker is now
  daemon-native on the web for both folders and files; the in-app folder browser
  remains only as the no-native-tool fallback for folders.
- macOS and Linux (with `zenity`/`kdialog`) get real dialogs everywhere; Windows
  and lean Linux hosts degrade to a typed path — the same degradation the folder
  picker already documents.
