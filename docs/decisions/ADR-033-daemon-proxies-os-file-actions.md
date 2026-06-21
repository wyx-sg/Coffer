# ADR-033 — Local Daemon Proxies OS File Actions (Web Matches Desktop)

> 中文版: [ADR-033-daemon-proxies-os-file-actions.zh.md](./ADR-033-daemon-proxies-os-file-actions.zh.md)

- **Status:** Accepted
- **Date:** 2026-06-21
- **Deciders:** Yuxing Wu
- **Spec:** [004-agent-registry](../../specs/004-agent-registry/spec.md) owns the `/fs` router and the shared FileActions bar (FR-038, FR-039 new); touches the open/reveal fallback clause in [005](../../specs/005-skill-manager/spec.md) FR-027 / FR-030 (new), [006](../../specs/006-knowledge-base/spec.md) FR-020, [007](../../specs/007-memory/spec.md) FR-021 — no new spec number; the `spec.md` files are updated before implementation.
- **Supersedes:** the "on the web, open/reveal falls back to copy-path" stance in 004 FR-009/FR-038, 005 FR-027, 006 FR-020, 007 FR-021.

## Context

Coffer's file viewers are **read-only** (specs 002/004/005/006/007): the user edits
in their own editor, reached through a shared `FileActions` bar that takes a managed
file (or its containing folder) to the OS — **open in external editor**, **reveal in
file manager**, **copy absolute path**.

Two distinct filesystem operations live behind these surfaces:

- **Picking** an input path — the agent `config_dir` (FR-023/FR-024) and the
  "添加 Skill" import path. Desktop uses the OS-native directory dialog; the web uses
  the daemon-backed folder browser (`GET /api/v1/fs/browse`). Both yield an absolute
  path.
- **Acting** on an existing path — open-in-editor / reveal-in-file-manager. The
  packaged desktop app (Tauri) performs the real OS action via `tauri-plugin-opener`;
  the **web** surface was specced to **fall back to copy-path**.

The web fallback rests on a premise stated in 006 FR-020 — *"the daemon cannot act on
the user's machine"* — and in `FileActions.tsx` — *"a browser cannot touch the
filesystem."* The browser half is true; the daemon half is **false for Coffer's
architecture**. The Coffer daemon is **loopback-only** (`127.0.0.1`) + token-guarded
(FR-024), so the web client is **always co-located with the daemon on the user's own
machine**. A local daemon process can open files and reveal them in the OS file
manager (`open` / `open -R` on macOS, `xdg-open` on Linux, `explorer /select` on
Windows) just as the desktop app can. The browser limitation only binds operations the
browser performs *directly*; Coffer always routes through a local daemon with full OS
reach.

Two concrete gaps follow:

1. On the web, the four read-only viewers (agent config files, skill files, memory
   facts, KB documents) show only "copy path" where the desktop shows real
   open/reveal — an avoidable downgrade, given the daemon is local.
2. The "添加 Skill" dialog never received the folder picker that the agent
   `config_dir` dialog has (FR-023/FR-024); it still requires the user to type the
   absolute path.

## Decision

**Route OS file actions through the local daemon so the web surface behaves like the
desktop app.**

### 1. Daemon FS-action endpoints (FR-039)

The daemon gains two write-side siblings of the read-only `GET /fs/browse`, under the
same loopback + token guard:

- `POST /api/v1/fs/open` `{ path, with? }` — open `path` in an application. `with` is
  the preferred-editor preference (002-ui-shell); when absent the OS default
  application is used. Serves both "open file in editor" and "open folder in editor".
- `POST /api/v1/fs/reveal` `{ path }` — select / reveal `path` in the OS file manager.

Both validate that `path` is **absolute and exists** before acting, and shell out with
an **argument vector** (never a shell string — no interpolation). An unopenable /
missing path returns an error, never a partial action.

### 2. FileActions performs real open/reveal on both surfaces (FR-038, parallel FRs)

The shared bar exposes one `useFsActions()` hook with `open(path, with)` /
`reveal(path)`:

- **Desktop** — `tauri-plugin-opener` (unchanged); on failure it falls back to the
  daemon endpoints.
- **Web** — the new daemon endpoints.

The preferred-editor value (a frontend `localStorage` setting,
`coffer.preferredEditor`) is passed in the request `with` field, so both surfaces open
in the same editor. The web surface now shows **exactly the desktop button set** —
open-file-in-editor, reveal-file-in-file-manager, open-folder-in-editor.

**copy-path is removed.** It existed only as the web's fallback when open/reveal could
not run; now that open/reveal run everywhere it serves no purpose, and a personal,
local-first tool keeps the surface minimal. The `copyPath` / `copyFolderPath` actions
and their i18n strings are deleted, not demoted.

### 3. "添加 Skill" gets the folder picker (FR-030)

The skill import dialog reuses the existing `FolderPicker` (native OS dialog on
desktop, daemon folder browser on web — FR-023/FR-024). The folder is **picked**, not
typed; the resolved absolute path feeds the unchanged `POST /skills/import`.

### 4. Picking keeps its dual path — deliberately

Unifying open/reveal but **not** the picker is intentional. The OS-native directory
dialog is a strictly better experience than the in-app daemon folder browser, and it
already ships on desktop (Agent config-dir). Only the web side uses the daemon browser.
We do not collapse the picker onto the daemon.

## Consequences

- Web now matches desktop for open/reveal across all four read-only viewer surfaces;
  consumers of `FileActions` are unchanged (they already pass `filePath` / `folderPath`).
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
