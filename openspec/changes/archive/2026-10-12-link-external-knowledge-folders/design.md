## Context

The decision and its alternatives are argued in ADR
`linked-knowledge-folders-are-read-only-and-machine-local`; this file records
only the shape of the implementation.

## Decisions

**One kind, two sorts, told apart by config.** A linked folder is an ordinary
`knowledge` resource whose config carries `folder`. `KnowledgeConfig` gains
that one optional field (absolute, normalised) and serialises without it for a
collection Coffer keeps, so existing rows stay `{}` on disk.
`linked_folder(config)` is the one test every caller uses.

**Storage class per row.** The `Kind` record's `storage_row` hook returns
`LOCAL` for a row that names a folder and `VAULT` otherwise, the same mechanism
that keeps agents and channels machine-local. The resource file writes the
home as `${HOME}` as every machine-local path does.

**Refuse at the service edge.** `KnowledgeService.collection_rows()` returns
only the collections Coffer keeps, so the sweep, the tidy-all hand-off and the
history never see a linked folder. `owned_collection(uid)` and
`require_collection(relpath)` raise `CollectionIsLinked` for one, which the
HTTP layer maps to 409; writes, tidy, check and description edits go through
them. Reads use `find_collection(relpath)`, which serves either sort and lets a
collection Coffer keeps win a name both hold (only a sync can produce that).

**A separate read module.** `infrastructure/knowledge/linked.py` lists, walks
and reads a linked folder with its own guard: a hidden segment, a backslash or
NUL, or a path that resolves outside the folder (a symlink out of it) is
refused. It is not `paths.py`, because that module guards the knowledge root
and refuses characters a person's own file names may hold. Titles come from
frontmatter `title`, else the first `# ` heading, else the file name.

**Bounded walks.** Hidden directories and `node_modules` are skipped, the walk
stops at 5000 Markdown files, and a file over 2 MB is described without its
body. A missing folder lists with no notes instead of failing the list.

**Guide section.** `_linked_lines` renders the folder's section with its path
home-relative, which keeps the render byte-identical across machines whose
home differs; at the counts-only budget level it lists the note count.

**Rename and disconnect.** `on_rename` does nothing for a linked folder (the
name is a label). `on_delete` skips `cleanup_collection` and only re-renders
the guide.

## Risks / Trade-offs

- The sweep's re-render, not the rename itself, updates the guide after a
  linked folder is renamed, so the old name can show for up to one sweep.
- A folder that moves on disk stays linked at its old path and lists with no
  notes until the person links it again.
- An agent can still write anywhere it likes with its own tools; the guide
  only tells it to follow the folder's rules file. Coffer is not a sandbox.
