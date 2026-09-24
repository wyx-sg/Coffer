# The Loopback Daemon Performs OS File Actions for the UI

**Status**: Accepted
**Date**: 2026-06-21
**Deciders**: Yuxing Wu
**Related**: [The Desktop Shell Hosts the Shared Frontend](desktop-shell-over-a-shared-frontend.md), [Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md), spec daemon "Open and reveal existing absolute paths", spec daemon "Browse folders without reading files", spec daemon "Open the host's native folder picker", spec agent-registry "Open config files in an external editor or reveal them", spec agent-registry "Offer a folder picker for a custom config directory", spec web-ui "Let the user choose an external editor", PRs #182, #190, #323

## Context

Coffer's file viewers are read-only by design: agent config files, skill
folders, knowledge files, memory files and native memory stores are shown, and
the user edits in their own editor. So every viewer needs a way to take a file
to the operating system — **open it in the user's editor** and **reveal it in the
file manager** — and several forms need the reverse, **picking a folder** and
getting its absolute path back (an agent's custom config directory, a skill
folder to import).

The UI is a web page, and a web page cannot do any of these. Browsers
deliberately withhold absolute paths and have no API to launch an application
or open Finder. But the premise "so the UI cannot do it" confuses the page with
the product. The daemon is bound to loopback only and every call carries its
token ([Daemon Auth and Origin Guard](daemon-auth-and-origin-guard.md)), so the
page talking to it is always on the same machine as the daemon, and the daemon
is an ordinary local process that can run `open` as well as any other.

The same UI also runs inside the desktop shell's webview
([The Desktop Shell Hosts the Shared Frontend](desktop-shell-over-a-shared-frontend.md)),
which could use native Tauri plugins. Whatever is chosen must work in both hosts
without splitting the frontend.

## Options Considered

### Option A — Daemon routes perform the OS action (chosen)

The daemon exposes the file actions as token-guarded HTTP routes under
`/api/v1/fs` (`backend/coffer/surfaces/http/fs_routes.py`, services in
`backend/coffer/application/fs/`):

- `POST /fs/open {path, with?}` opens a path in the named editor, or the OS
  default; `POST /fs/reveal {path}` selects it in the file manager. macOS uses
  `open` / `open -a <app>` / `open -R`, Windows `explorer /select,`, Linux
  `xdg-open` — where Linux has no portable "select this file", reveal opens the
  containing folder.
- `GET /fs/editors` lists the GUI editors actually installed on this host
  (app bundles under `/Applications` and `~/Applications` on macOS, commands on
  `PATH` elsewhere), each with the exact value `/fs/open`'s `with` accepts, so
  the Settings editor picker offers real choices instead of a free-text field.
  The chosen editor is a per-browser preference (`coffer.preferredEditor`).
- `POST /fs/pick-folder` opens the host's native directory dialog (`osascript`
  on macOS, `zenity` or `kdialog` on Linux) and returns `{available, path}`.
  Where there is no argv-only dialog — Windows, or a Linux host with neither
  tool — it answers `available: false` and `FolderPicker` falls back to the
  in-app browser over `GET /fs/browse`, which lists subdirectories and never a
  file.

On the frontend, `useFsActions()` in `frontend/src/lib/fsActions.ts` is the one
way to call open/reveal; `components/FileActions.tsx` renders the bar every
viewer uses; `components/FolderPicker.tsx` (through `FolderPickerField`) serves
the agent forms and the skill import dialog.

Pros: works in any browser and in the webview unchanged, because both reach a
loopback route the same way; one implementation per OS, in the process that
already does local filesystem work; the frontend has no host branches. Cons: the
daemon gains routes that launch processes, so they must be fenced (see
Decision); and a Windows host gets no native folder dialog. It wins because it
is the only option that does the real action in both hosts with one code path.

### Option B — Copy the path and let the user do the rest

Each viewer offers "copy absolute path"; the user pastes it into their editor or
Finder. This was the specced behaviour for the browser host before this
decision, on the stated premise that the daemon "cannot act on the user's
machine". Pros: no OS surface at all. Cons: every open is three manual steps,
and the premise is false for a loopback daemon. It loses on usability once the
premise falls. Copy-path was deleted outright rather than kept as a fallback,
since open and reveal always run.

### Option C — Native Tauri `dialog` and `opener` plugins in the shell

The desktop shell calls the OS directly through Tauri plugins, with the browser
host on something else. This is what the desktop shell did before PR #317.
Pros: a genuinely native call with no HTTP hop. Cons: it covers only the desktop
host, so the browser still needs Option A or B; it puts an `isTauri()` branch in
every file component, which is what made the frontend expensive to change; and a
webview already reaches the daemon routes exactly as a tab does. It loses
because it adds a second path for nothing a user can perceive; `desktop/Cargo.toml`
deliberately declares neither plugin.

### Option D — The browser's File System Access API

`showDirectoryPicker()` / `showOpenFilePicker()` give the page a handle to a
user-chosen directory or file. Pros: no daemon route; the browser mediates
consent. Cons: a handle is not an absolute path, and an absolute path is exactly
what an agent config directory or a skill import needs; the API cannot launch an
editor or reveal anything; and it is Chromium-only — Safari, and so the macOS
WKWebView the desktop shell runs in, does not expose the pickers. It loses on
all three counts.

### Option E — Also proxy native open-file and save-file dialogs

Add `pick-file` and `save-file` routes beside `pick-folder`. They were built on
2026-06-21 and deleted in PR #323. Pros: one uniform native-dialog family. Cons:
the browser already has both — `<input type="file">` opens a file and hands the
page its contents rather than a path the daemon must then read, and
`<a download>` saves one. It loses because only a folder needs the daemon: the
browser withholds its absolute path, and registering an agent requires it.

## Decision

**OS file actions are daemon routes, the same in the browser and in the desktop
shell: open, reveal, list installed editors, and one native dialog — the folder
picker.** Every such route must:

- be guarded by the same loopback bind and token as every daemon route;
- accept only a path that is absolute and exists, answering
  `FS_PATH_NOT_OPENABLE` (400) otherwise, before anything is launched;
- launch with a fixed argument vector, the path as one element of it, never a
  shell string;
- create nothing.

No open-file or save-file dialog is proxied, and the desktop shell implements
none of these natively (spec desktop-app "Reimplement no daemon route in the
shell").

## Consequences

- Every read-only viewer offers real open-in-editor and reveal, in both hosts,
  through one hook and one bar.
- The daemon has a process-launching surface. It adds no new reach: the page
  could already list the local filesystem through `GET /fs/browse` at the same
  trust level, and these routes act on a path the user navigated to.
- Windows has no native folder dialog and Linux reveal opens the folder rather
  than selecting the file; both degrade to something that works rather than an
  error. The `available: false` path is not exercised in CI.
- Adding a new OS action means a daemon route with the four rules above, never
  a Tauri plugin or a browser API branch.
