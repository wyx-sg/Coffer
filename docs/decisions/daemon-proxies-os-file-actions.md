# Local Daemon Proxies OS File Actions

**Status**: Accepted
**Date**: 2026-06-21
**Deciders**: Yuxing Wu
**Spec**: the `/fs` router (now spec daemon FR-021) and the shared FileActions bar (now spec [agent-registry](../../specs/agent-registry/spec.md) FR-047) are new here; this touches the open/reveal fallback clause on three other viewers — the skill file viewer and the "添加 Skill" folder picker, both of which spec [skill-manager](../../specs/skill-manager/spec.md) now states as assumptions rather than requirements of its own; the document viewer (now spec [knowledge](../../specs/knowledge/spec.md) FR-040); and the fact viewer (now spec [memory](../../specs/memory/spec.md) FR-029) — no new spec; the `spec.md` files are updated before implementation.
**Supersedes**: the "on the web, open/reveal falls back to copy-path" stance in spec agent-registry FR-044 / FR-047, in the skill file viewer's open/reveal clause (spec skill-manager, since restated as an assumption), in the retired Knowledge Base spec's document-viewer requirement (now spec knowledge FR-040) and in the retired Memory spec's fact-viewer requirement (now spec memory FR-029).

## Context

Coffer's file viewers are **read-only** (the UI Shell, Agent Registry, Skill Manager, Knowledge Base and Knowledge Layer specs): the user edits
in their own editor, reached through a shared `FileActions` bar that takes a managed
file (or its containing folder) to the OS — **open in external editor**, **reveal in
file manager**, **copy absolute path**.

Two distinct filesystem operations live behind these surfaces:

- **Picking** an input path — the agent `config_dir` (spec agent-registry FR-050 /
  spec daemon FR-019) and the
  "添加 Skill" import path. The UI picks it through the daemon-backed folder browser
  (`GET /api/v1/fs/browse`), which yields an absolute path.
- **Acting** on an existing path — open-in-editor / reveal-in-file-manager. This was
  specced to **fall back to copy-path**, on the premise that a browser-hosted UI
  cannot reach the OS at all.

That fallback rests on a premise stated in the retired Knowledge Base spec's document-viewer requirement — *"the daemon cannot act on
the user's machine"* — and in `FileActions.tsx` — *"a browser cannot touch the
filesystem."* The browser half is true; the daemon half is **false for Coffer's
architecture**. The Coffer daemon is **loopback-only** (`127.0.0.1`) + token-guarded
(spec daemon FR-019), so the web client is **always co-located with the daemon on the user's own
machine**. A local daemon process can open files and reveal them in the OS file
manager (`open` / `open -R` on macOS, `xdg-open` on Linux, `explorer /select` on
Windows) exactly as any native process on that machine can. The browser limitation only
binds operations the browser performs *directly*; Coffer always routes through a local
daemon with full OS reach.

Two concrete gaps follow:

1. The four read-only viewers (agent config files, skill files, memory facts, KB
   documents) show only "copy path" instead of real open/reveal — an avoidable
   downgrade, given the daemon is local.
2. The "添加 Skill" dialog never received the folder picker that the agent
   `config_dir` dialog has (spec agent-registry FR-050 / spec daemon FR-019); it still requires the user to type the
   absolute path.

## Decision

**Route OS file actions through the local daemon, so the browser-hosted UI performs
real OS actions.**

> **2026-09-09:** this ADR originally described a second, native branch for
> open/reveal (`tauri-plugin-opener` inside the packaged desktop shell). That shell was
> removed and the daemon endpoints below are now the single mechanism.
>
> **2026-09-12:** the desktop shell is back ([The Desktop Shell
> Returns](./desktop-shell-over-a-shared-frontend.md)) and the native branch is
> **deliberately not**. A webview reaches a loopback HTTP route exactly as a
> browser tab does, so the daemon endpoints already work inside the shell;
> restoring the plugin path would buy nothing a user could perceive and would
> cost the `isTauri()` fan-out this ADR's consolidation removed. The endpoints
> below remain the single mechanism, now for both hosts (spec desktop-app FR-011).

### 1. Daemon FS-action endpoints (spec daemon FR-021)

The daemon gains two write-side siblings of the read-only `GET /fs/browse`, under the
same loopback + token guard:

- `POST /api/v1/fs/open` `{ path, with? }` — open `path` in an application. `with` is
  the preferred-editor preference (web-ui); when absent the OS default
  application is used. Serves both "open file in editor" and "open folder in editor".
- `POST /api/v1/fs/reveal` `{ path }` — select / reveal `path` in the OS file manager.

Both validate that `path` is **absolute and exists** before acting, and shell out with
an **argument vector** (never a shell string — no interpolation). An unopenable /
missing path returns an error, never a partial action.

### 2. FileActions performs real open/reveal (spec agent-registry FR-047, parallel FRs)

The shared bar exposes one `useFsActions()` hook with `open(path, with)` /
`reveal(path)`, both backed by the daemon endpoints above.

The preferred-editor value (a frontend `localStorage` setting,
`coffer.preferredEditor`) is passed in the request `with` field. The bar shows the full
button set — open-file-in-editor, reveal-file-in-file-manager, open-folder-in-editor.

**copy-path is removed.** It existed only as the fallback for when open/reveal could
not run; now that open/reveal always run it serves no purpose, and a personal,
local-first tool keeps the surface minimal. The `copyPath` / `copyFolderPath` actions
and their i18n strings are deleted, not demoted.

### 3. "添加 Skill" gets the folder picker (spec skill-manager, `## Assumptions`)

The skill import dialog reuses the existing `FolderPicker` (the daemon-backed folder
browser — spec agent-registry FR-050 / spec daemon FR-019). The folder is **picked**, not typed; the resolved absolute
path feeds the unchanged `POST /skills/import`.

### 4. Picking stays out of scope here — since retired

This ADR unified open/reveal but not *picking*: at the time an OS-native directory
dialog was available only inside the packaged native shell, so the browser UI kept the
in-app daemon folder browser. The native shell is gone, and the daemon now opens the
host's native **directory** dialog itself (spec daemon FR-020). It does not proxy an
open-file or save-file dialog: the browser's own `<input type="file">` and
`<a download>` cover those, and the first is better — it hands over the file's
contents rather than a path the daemon must then read. A folder is the exception,
because the browser deliberately withholds absolute paths.

## Consequences

- Real open/reveal now runs across all four read-only viewer surfaces; consumers of
  `FileActions` are unchanged (they already pass `filePath` / `folderPath`).
- The false "daemon cannot act on the user's machine" premise is removed from the
  touched FRs; the rationale becomes "the loopback daemon is on the user's machine, so
  it acts on the user's behalf".
- New OS-action surface area on the daemon. Mitigated by: loopback + token guard
  (same as every daemon route), absolute-and-exists path validation, argument-vector
  shell-out (no injection), and the fact that `GET /fs/browse` already exposes the
  local filesystem at the same trust level — this adds *acting on* a path the user
  navigated to, not new reach.
- Cross-platform reveal has no universal "select the file" primitive on Linux; the
  daemon degrades to opening the containing folder there. macOS (`open -R`) and
  Windows (`explorer /select`) select the item.
- Consistent with the personal-tool, local-first posture (ADR-/constitution): the
  daemon already performs local filesystem work on the user's behalf; opening a path
  the UI surfaced is benign and single-user.
