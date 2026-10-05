## Context

The product decision is fixed by the owner (2026-10-05): a read-only history of
knowledge documents and skills inside Coffer, read from the vault's git
repository, and a restore that Coffer performs itself. The editors, save
routes, fingerprints, leave guard, sync-conflict views and skill-update merge
that `hand-files-to-external-tools` removed stay removed. This file records how
the history comes back and the choices left open.

## Decisions

### One set of vault routes serves both kinds

Before #534 there were two parallel histories: `/knowledge/history*` (a
document's versions, its body at a version, restore through the knowledge
service) and `/vault/history|diff|content|restore|changes` (any vault path,
used by skills). Only the second comes back. A knowledge document is a vault
file at `knowledge/<collection>/<path>` and a skill's master folder is
`skills/<name>/`, so one generic service answers both and the knowledge
package keeps no history code of its own. Knowledge's changes feed and
restore-a-delete (`/knowledge/changes*`) stay as they are, because the delete
toast's Undo reads them.

Recovered from `fc9d316c4^` and adapted:

- `application/vault/history_service.py` — `versions`, `restore` and the
  secret refusal come back nearly verbatim; `content`, `current`, `changes` and
  `problems` do not (nothing calls them: `/vault/problems` reads the writer
  directly, as it does on main).
- `VaultHistoryPort` and `VaultRepository.diff` come back; `later` does not.
- `vault_schemas.py` — `VaultVersionOut`, `VaultPathChangeOut`,
  `VaultHistoryOut`, `VaultRestoreIn/Out` and `version_out` come back.
- Frontend: `VersionHistorySplit` verbatim; `unifiedDiff` moves to
  `lib/diff/`; `versionLabels` and `vault/writers` merge into
  `lib/vault/versionLabels.ts` and word a file as well as a folder;
  `useVaultHistory` and `lib/api/vault.ts` come back on the current
  `unwrap` client.

### A version's diff is one route with two readings

The old UI read a version's change one file at a time (`/vault/diff` per file)
and built Compare with current in the browser from `/vault/content` and
`/knowledge/history/version`. Now `GET /vault/diff?path&version&against`
answers every file at once: `previous` is what the version changed (`git show`
per file it touched), `current` is how the path differs now from how that
version left it (`git diff <version> HEAD` per file whose blob differs). Both
work for a file and a folder, so the skill history gains Compare with current
too, and the browser needs no diff algorithm.

### Restore states the newest version it saw, not a fingerprint

The old file restore took the fingerprint of the bytes the caller last read,
which needed `/vault/content`; a folder restore compared against `HEAD`. Both
now take `expected_current`: the newest version the History tab listed. The
service first commits a pending edit on disk under the path (as a `disk`
write), then refuses `VAULT_FILE_STALE` if the newest commit touching the path
is not the one the caller saw, and writes every file with `Expect.HEAD`. A
person who edited the document in their editor after opening History is told
it changed instead of losing the edit. The restore is one new commit with
`Coffer-Operation: restore` and `Coffer-Restored-From`, the writer from the
request's actor (a person through the web UI is `user`), and is audited
`vault_file_restored` — an event that kept its enum value and Activity label
for exactly this.

### Reads settle what changed on disk

`versions` and `diff(against=current)` commit the pending edits under the path
before reading, so a document edited in the person's editor shows that edit as
the newest version (writer `disk`) without waiting for the scanner. A hand edit
validation refuses stays out of `HEAD`, as everywhere.

### Tab, not dialog

The house rule (`.agents/frontend.md`, "A page only when there is a page's
worth") puts a list of versions beside a diff in a tab: it is a page's worth of
content with its own action. A knowledge document's pane carries **Document**
and **History** in its bar (the tab is the path segment, as before #534); a
skill gets a fourth tab, **History**, after Requires. Coffer's own skill keeps
the tab with an empty state saying it has no history, so every skill has the
same four tabs. The History… items leave both ⋯ menus, because a menu never
repeats what is on the surface.

Restore this version… opens the shared `ConfirmDialog`, not the 1060 review
the old skill restore used: the diff is already on screen behind it (Compare
with current shows exactly what the restore changes), so the dialog only says
that the result is a new version and, for a folder, that files added since are
removed. A refusal stays in the dialog.

### The restore hand-off goes

`POST /vault/history/handoff` existed only to hand a restore to an agent. Coffer
now restores itself, and nothing else calls it, so the route, its schemas, its
prompt (`domain/vault/handoffs.py`) and `VaultHistoryDialog` are deleted rather
than kept unused.

### Recent changes stays out

The Knowledge page's Recent changes was a cross-collection timeline with
collection and author filters and a Restore on each delete. It does not fall
out of this change: it needs its own view, filters kept in the URL and the
per-change restore wording, and the per-document History tab already answers
"who changed this and what". A delete is still undone from its toast; after
the toast a deleted document has no page to open its History from, so it is
brought back with git (`git -C ~/.coffer/vault log -- knowledge/<path>`), and a
collection delete still asks first. This can come back later on top of the
same feed if it is missed.

## Risks

- A folder restore of a large skill writes every file that differs in one
  commit; it goes through the vault validator like any write, so an invalid
  result is refused whole.
- `diff(against=current)` reads `HEAD`, not the working tree: a hand edit the
  validator refused is not part of "current". That is the same `HEAD` every
  other surface treats as current.
