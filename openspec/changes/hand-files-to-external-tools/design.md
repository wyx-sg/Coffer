## Context

The product decisions are fixed by the owner: viewing stays, editing, history
browsing and merging go to the editor, git or an agent. This file records how
it is built and the choices left open.

## Decisions

### Specs move with the code, phase by phase

As in the previous removal: each phase deletes from `openspec/specs/` the
requirements this change REMOVES once their tests are gone, test markers may
name scenarios this change ADDs or MODIFIES while it is in flight, and at the
end the main specs are restored to their state before the change and the
change is archived, which applies every delta at once. A requirement that
loses a scenario is REMOVED and ADDED again under a new title.

### Coffer's own config writes keep backup and compare-and-swap

`ConfigFileStore.write_text_atomic` (temp file and rename, a backup under
`~/.coffer/config-backups/`, the optional expected fingerprint) is what every
Coffer writer uses — connect, repair, plugin toggle, MCP install and remove,
provider projection, the reconciler. Only the user-edit layer goes:
`AgentConfigFileService.read_file/write_file/read_child/write_child/delete_child`,
`validate_content`, `validate_child_relpath`, the content and write models,
`resolved_within`, `remove_tree` (already dead) and the two audit events
`agent_config_file_written` / `agent_config_file_deleted`. `CONFIG_FILE_STALE`
stays because a projection or model switch raises it. The rule those writers
rely on moves from "Write config files atomically with a backup and an audit
entry" and "Reject stale config-file writes by fingerprint" to one ADDED
requirement, "Back up and compare-and-swap every write Coffer makes to an
agent's config", which provider-switching cites.

The list keeps a directory entry's children (`agents/` subagents) as rows, so
each subagent file can be opened. A row whose file does not exist yet offers
no Open in editor (`/fs/open` creates nothing) and reveals its folder.

### Audit vocabulary stays readable

Events nobody emits any more — `agent_config_file_written`,
`agent_config_file_deleted`, `memory_note_edited`, `vault_file_restored` — keep
their enum values and their Activity labels, because the audit log is kept and
recorded rows must still read in plain words. The enum comment says they are no
longer emitted.

### History becomes a hand-off

`POST /api/v1/vault/history/handoff` takes a vault-relative `path` (a file, or
a folder ending in `/`) and an optional `at` time, and answers the absolute
path, the vault path, the `git -C <vault> log -p -- <path>` command and the
prompt. The prompt (built in `domain/vault/handoffs.py`, rendered by
`render_handoff` like every other) states:

- the file or folder and, when given, the time to bring it back to (otherwise:
  list its recent versions and ask which one);
- the vault is a git repository at that path, and history is never rewritten
  (no reset, amend, rebase or force push);
- write the earlier content back into the working tree, touch only that path,
  and make one new commit whose message carries `Coffer-Writer: agent`,
  `Coffer-Operation: restore` and `Coffer-Restored-From: <commit>` — the
  trailers every vault commit uses to name its writer
  ([ADR](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md));
- tell the person what was restored.

It carries no secret and refuses a path under `secret/` (`VAULT_PATH_REFUSED`,
as the old restore did). The route sits on the vault router beside
`/vault/problems`, which stays. `VaultHistoryService`, its port, the version
and diff models and `VAULT_VERSION_NOT_FOUND` go.

The web UI's **History…** item (a knowledge document's ⋯ menu, a skill's ⋯
menu) opens one dialog: the vault-relative path, an optional date and time,
**Copy git command**, **Reveal in Finder** and the hand-off split button.
Coffer's builtin skill is not in the vault and offers no History.

### Knowledge keeps Undo; a collection delete asks first

The delete toast's Undo reads the changes feed for the delete's version and
restores it (`GET /knowledge/changes`, `POST /knowledge/changes/{version}/restore`),
so both routes stay, and so does `PUT /knowledge/collections/{uid}/description`
(the in-place description edit is a collection property, not a document
editor). They move from `history_routes.py` to the knowledge routes and a
smaller service; the per-document history, version body, version diff and
version restore go. With Recent changes gone, a deleted collection can only
be brought back while its toast is open — git can bring its files back, but
not its registration — so **Delete collection** now asks first. A document
delete still happens at once with Undo: after the toast, its file is one
`git` restore away (the History hand-off).

The document's "created … by …" line reads the frontmatter (`created_at`,
`actor`) instead of the oldest history version.

### Memory and skills

`PUT /memory/partitions/{uid}/notes/{slug}`, `NoteSave`, the note fingerprint,
`MEMORY_NOTE_CONFLICT` and `note_edit.save_body` go (the distil test that used
`save_body` writes the file directly). `PUT /skills/{uid}/files/content`,
`content_ops.py`, `SkillFileWriteRequest`, the read's `fingerprint` and
`SKILL_FILE_STALE` go. A skill whose master folder is gone keeps its banner
with the hand-off of "Hand unsettled skill drift to an agent with a prompt";
the in-app Restore from History goes, and the prompt points the agent at the
vault's git history.

### Sync conflicts

There never was a line-by-line merge editor; the in-app parts are the live
"file as saved" view under **Editing in your editor** and the diff of an
agent's merge. Both go, with `FileVersionsOut.base`, `edited`, `merged` and
`merged_diff`. What stays is everything a person answers with: the two
choices with the take-theirs diff (a preview of Coffer's own write), **Open in
editor** on the marked-up copy under `derived/sync-conflicts/`, the hand-off,
**Mark resolved** (the `edited` answer, read from the copy and refused while a
marker is left) and **Back to two choices**. A merged-by-agent file says the
agent merged it and to check the copy in the editor before marking it
resolved.

The held-deletion review keeps its stop: the page lists the files by folder
and offers **Keep the files** and **Delete N files** as two buttons; the
second dialog that repeated the facts goes, because the page already names
them.

### Shared code kept and deleted

Kept: `ChangePreview`, `ChangePreviewBody`, `ChangeTargetList`, `WhatWillHappen`,
`FileDiff` (also drawn by skill update/copy reviews and the custom-tool
reimport), `OpChip`, `LineCounts`, `lib/diff/wrapLine`, `lib/knowledge/lineDiff`
(skill `textDiff`, custom-tool `specDiff`), `ReadOnlyFile`, `FileBody`,
`ViewerToolbar`, `FileTree`, `FileBrowserFrame`.
Deleted: `components/history/`, `KnowledgeHistoryTab`, `KnowledgeVersionPanel`,
`KnowledgeCompareView`, `KnowledgeRecentChanges`, `KnowledgeChangeRow`,
`KnowledgeDocumentEditor`, `KnowledgeWriterMark` (if unused),
`SkillHistoryTab`, `SkillVersionPanel`, `SkillRestoreDialog`,
`SkillFileEditing`, `SkillFileConflict`, `reverseDiff`, `useVersionDiffs`,
`versionLabels`, `lib/knowledge/unifiedDiff`, `lib/knowledge/documentConflict`,
`lib/knowledge/dirtyDocument`, `lib/vault/writers`, `useVaultHistory`,
`useKnowledgeHistory` (what Undo and the description need moves to
`useKnowledge`), `useFileDraft`, `useUnsavedGuard`, `useBeforeUnload`,
`components/shell/UnsavedGuard`, `FileTextEditor`, `LineEditor`,
`FileConflictBanner`, `ConfigEditorPane`, `ConfigEditorNotices`,
`NewConfigFileDialog`, `useConfigEditorState`, `useConfigDirFiles`,
`SyncConflictEditing`, `SyncConflictMerged` (replaced by one small card).

### New documents

There is no web entry that creates a knowledge document or a memory note, and
knowledge's spec forbids a route that creates a document at a path. None is
added: a person drops Markdown into the collection's folder (Reveal in Finder)
or uploads; the agent writes files. The agent config "New file" dialog is
deleted with the rest of the editor.

## Risks

- A person who relied on the web editor now needs an editor. Open in editor
  uses their preferred editor (Settings › General).
- The History hand-off trusts the agent to commit as described. A wrong commit
  is a commit like any other: the vault validates it and the next one fixes it.
