## Why

The desktop tray menu (Open Coffer, Sync status, Restart daemon, Quit Coffer) was English-only. A user who set the interface to Chinese still got an English tray, and the sync alert's tray label, tooltip and notification were English too.

## What Changes

- The tray, its tooltip and the sync notification speak the interface language the user chose in the web UI (English or Chinese), using the web UI's own terms.
- The page reports its language to the shell through a new IPC command, `set_ui_language`, when it starts and on every switch; the tray relabels at once, without a restart.
- Before the page has reported, the tray follows the OS language, which is also what the page falls back to.

## Capabilities

### New Capabilities

### Modified Capabilities
- `desktop-app`: "Host the UI locally in an application window" gains the tray-language rule and a scenario; "Consume the one frontend build the daemon serves" sanctions the language report.

## Impact

- Desktop shell: new `tray_locale.rs`; `tray.rs` builds and relabels the menu per language and registers `set_ui_language`; `sync_presentation.rs` and `sync_watch.rs` word the sync alert per language; `sys-locale` dependency for the OS language.
- Frontend: `lib/tauri.ts` reports the language (`followLanguageInShell`), called from `main.tsx`.
- Docs: desktop-app guide, spec Purpose, capability description, `.agents/stack.md` module list.
