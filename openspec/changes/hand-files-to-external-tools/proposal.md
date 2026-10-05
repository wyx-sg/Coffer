## Why

The principles say Coffer is **not a second agent**: what a coding agent, an
editor or git already does, Coffer does not rebuild. The web UI carried a text
editor for knowledge documents, memory notes, skill files and the agents' own
config files — with a fingerprint check, a stale-save banner, a compare view,
a line-number editor, a new-file dialog and a guard against leaving with
unsaved edits — and a version browser for knowledge and skills (History tabs,
version panels, compare with current, restore, Recent changes). Every one of
those is something the person's editor, git, or their agent does better, on
the files Coffer already names by path. The previous change did the same for
the web chat.

What only Coffer can do stays: listing what an agent holds, writing Coffer's
own entries with a preview first, settling a sync round, and the safety rule
that stops a round that would delete too much.

## What Changes

- **Agent config files** (`~/.claude/*`, `~/.codex/*`): the Config files tab
  becomes a read-only list — name, location, size and modified time — whose
  rows offer **Open in editor** and **Reveal in Finder**. Removed: the viewer
  and editor, Revert/Save, JSON validity line, the stale-write panel, New file,
  Delete, and the routes `GET`/`PUT /agents/{uid}/config-files/{key}` and
  `GET`/`PUT`/`DELETE …/files/{relpath}` with their two audit events. The
  Hooks tab stays read-only; its file links open the file in the editor
  instead of the Config files tab; Coffer's hook keeps its state and Repair.
  The atomic write, backup and compare-and-swap that Coffer's own writes use
  (connect, repair, plugin toggle, MCP install, provider projection) stay,
  under a requirement of their own.
- **Knowledge documents, memory notes, skill files**: read-only previews
  (Preview / Source) with **Open in editor** and **Reveal in Finder**. Removed:
  Edit, the editor, ⌘S, the stale-save banner, Compare (Keep my edit / Take the
  version on disk), Copy my text, Reload, the unsaved dot and the leave guard;
  `PUT /knowledge/file`, `PUT /memory/partitions/{uid}/notes/{slug}`,
  `PUT /skills/{uid}/files/content`, their fingerprints and the conflict codes
  `KNOWLEDGE_FILE_CONFLICT`, `MEMORY_NOTE_CONFLICT`, `SKILL_FILE_STALE`.
  Agents and other programs keep writing the same files at the same paths.
- **History**: a knowledge document's History tab, a skill's History tab, the
  version panels, Compare with current, Restore this version, the Knowledge
  page's Recent changes, and the routes behind them (`/knowledge/history*`,
  `/vault/history`, `/vault/diff`, `/vault/content`, `/vault/restore`,
  `/vault/changes`) go. In their place a **History** dialog shows where the
  file sits in the vault, copies `git -C <vault> log -p -- <path>`, reveals the
  file, and hands the restore to the person's agent with a prompt the daemon
  builds (`POST /api/v1/vault/history/handoff`): the file, the time asked for,
  that the vault is a git repository, and how a vault commit names its writer.
  The audit log keeps who changed what and when. A knowledge delete keeps its
  toast **Undo** (the feed and restore-a-delete route it reads stay).
- **Sync conflicts**: the in-app "file as saved" view and the diff of an
  agent's merge go. Each conflict keeps **Keep this Mac's**, **Take <machine>'s**
  (with what it changes here), **Open in editor** on the marked-up copy, the
  hand-off to an agent, **Mark resolved** and **Back to two choices**. A held
  deletion keeps its stop and asks once: two buttons, no second dialog.
- **Shared diff code** keeps only what Coffer's own write previews and
  update reviews draw. `components/history`, the knowledge version and compare
  views, `reverseDiff`, `useVersionDiffs`, `unifiedDiff`, `lib/vault/writers`,
  `useFileDraft`, `FileTextEditor`, `LineEditor`, `FileConflictBanner` and the
  unsaved-edits guard are deleted.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-registry` (+ `claude-code`, `codex`): read-only config-file list;
  editing, directory-child reads and writes and the stale check of user edits
  removed; Coffer's own writes keep backup and compare-and-swap.
- `knowledge`: no save route; read-only document pane; history routes removed
  except the feed and restore-a-delete behind Undo; a collection delete asks
  first.
- `memory`: no edit route; a memory is read-only on its page.
- `skill-manager`: no file write; Files, Delivery and Requires tabs; History
  as a hand-off.
- `vault-storage`: version browsing and restore routes removed; the restore
  hand-off added; refused hand edits keep their list.
- `vault-sync`: conflict views trimmed; held deletions confirmed once;
  restore to a revision is a new commit written outside Coffer.
- `web-ui`: leave guard, History tabs, version split, Recent changes and the
  knowledge "needs git" rows removed; one diff renderer kept; the History
  dialog added; Skills page tabs.
- `daemon`: the consumers of `/fs/open` named anew.

## Impact

- **Removing shipped behaviour** (principles, Governance). See the PR
  description for the reversal cost; in short: no migration and no user data
  touched (files stay where they are, git history and audit rows stay); the
  deleted modules are in git history; specs, data models, ADR headers and the
  docs site (en + zh) are rewritten.
- Backend: `surfaces/http/{agent_config_routes,knowledge/history_routes,knowledge/routes,memory/note_routes,skill_file_routes,vault_routes,sync_stop_*}`,
  `application/{agent/config_file_service,knowledge/history_service,knowledge/service,memory/service,skill/content_ops,vault/history_service,sync/*}`,
  domain errors, audit vocabulary comments.
- Frontend: `components/{files,knowledge,memory,skills,agents,history,change-preview,shell}`,
  `pages/sync`, `lib/{hooks,knowledge,vault,api}`, i18n.
- Canvas (not editable from a cloud session; listed in the PR): Agents
  (Config files, Hooks), Context (knowledge document, History, Recent changes,
  memory), Capabilities (skill Files and History), System (sync conflicts,
  held deletions), Foundations (leave guard dialog, version split).
