## Context

Knowledge (`~/.coffer/vault/knowledge/`) and memory (`~/.coffer/derived/memory/`)
are already plain Markdown trees, and agents already read and edit them with
their own file tools. On top of the files sit an MCP tool (`coffer__write`),
two CLI groups, `coffer path` targets, a REST family kept in parity with the
CLI, and memory triggers. The measured use of the first and the last is close
to zero (four `coffer__write` calls in thirty days; zero trigger fires, zero
armed triggers). This change removes what only re-exposes the files, removes
triggers, and drops the writer as a source of authority.

## Goals / Non-Goals

**Goals:**

- Agents change knowledge and memory only through files; people through files
  or the web UI.
- No statement is protected because of who wrote it.

**Non-Goals:**

- Changing retrieval, the session-start index, aggregation, distil routing or
  curation's bounds.
- The CLI rule for every other kind; that is `trim-the-cli-to-what-needs-it`.
- Syncing memory or making memory edits survive a rebuild of the derived tree.

## Decisions

### 1. An agent adds knowledge by writing a file into the inbox

The contract is a path and a shape: `<collection>/.inbox/<any-name>.md`, with
optional frontmatter. The sweep already commits files changed on disk once
they have been quiet; it now also recognises a new inbox file that no Coffer
surface wrote and **normalises** it before committing:

- `title` — kept, else the first `# ` heading, else the file name's stem;
- `description` — kept, else the first prose paragraph, else the title (the
  same fallback uploads use);
- `actor` — kept as written (self-reported), else `agent`;
- `created_at` / `updated_at` — kept, else the time the sweep saw the file;
- every other key a writer set is kept.

It records one `knowledge_written` audit event per item, with
`actor_reported: true` when the actor came from the file. A Markdown file in a
top-level directory that is not a collection is left alone and is not
catalogued; only a person creates a collection. A non-Markdown file in an inbox
is left in place, logged, and not curated.

*Alternative rejected:* keep `coffer__write` for attribution. The gateway did
know the calling agent, but the tool went unused, and an unused tool attributes
nothing.

### 2. Newer or better-evidenced wins; the writer confers nothing

Curation's instruction becomes: where two statements disagree, the newer one
wins unless the older one is shown to be right — by a source, a date, a
command's output, or the code — and the superseded statement stays legible with
the date it changed. An out-of-band edit to a document (a person in the web UI
or an editor, or an agent's file tools) is still owed a pass, which carries it
outward into documents that disagree, **as a newer statement**, not as an
untouchable one: a later item may correct it like anything else.

Two code-level guards stay, because they protect data rather than a writer: a
pass never overwrites a file whose bytes changed after it read them, and a
rewrite keeps every frontmatter key it did not set.

Distil follows the same rule for memory. Undo and per-version restore remain
the recovery path for knowledge; for memory, `.raw/` remains the input a
rebuild starts from.

### 3. Memory notes are editable

The partition page's selected memory gains **Edit**, backed by
`PUT /api/v1/memory/partitions/{uid}/notes/{slug}`: it replaces the body,
keeps the frontmatter, stamps `updated_at`, and takes the fingerprint the read
returned — a note changed since (by distil or on disk) is refused with a
conflict carrying the current body, exactly as the knowledge editor's save is.
It records `memory_note_edited`. An edit on disk needs nothing: the note is the
file.

An edited note is the current body the distil writing stage receives the next
time an entry is routed to it, so the edit persists until newer evidence
revises it. The derived tree is still disposable: deleting it and rebuilding
loses edits. That is what deleting derived data means, and the guide says so.

### 4. Triggers are removed, and the hook shrinks to two entries

Removed: the trigger domain, store, service and routes; `vault/memory-triggers/`;
the distil writing stage's proposal fields; the hook service's guard and error
paths; the CLI hook's local trigger read; the session ledger's trigger keys;
the `memory_trigger_*` audit events and the `guard` / `error` moments.

Upgrade needs no person: a one-time migration deletes `vault/memory-triggers/`
(a vault deletion that syncs like any other), and the reconciler, which already
compares the set of events Coffer's entries sit on, rewrites every installed
hook from four entries to two. The two entries keep their command and their
positions, so Codex's per-entry approvals for them still match.

### 5. The knowledge and memory REST routes are the web UI's

The knowledge and memory REST routes stay in the OpenAPI contract, because the
frontend's types are generated from it, but they are the web UI's private
interface: the REST reference leaves them out and no requirement promises them
to anything else. `coffer memory hook` and `POST /api/v1/memory/hook` are the
one CLI command and one route of these two kinds that a program other than the
web UI calls; the command is hidden from help and the references. The rule
that decides which CLI commands exist at all is the companion change
`trim-the-cli-to-what-needs-it`, which this change is archived before.

## Risks / Trade-offs

- [An agent writes a malformed inbox file] → normalisation fills what is
  missing; a file it cannot read as text stays in place and is logged.
- [A wrong edit is no longer protected and a wrong pass can overwrite a right
  one] → the evidence clause in the instruction, the history, per-version
  restore and whole-pass undo.
- [Memory edits vanish on a rebuild] → stated in the guide; a rebuild is a
  deliberate act.
- [Scripts that called the removed commands break] → none known outside
  Coffer's own tests; the CLI reference lists what remains.
- [Codex approvals drift if positions shift] → verified by a test that reads
  the rewritten `hooks.json` and recomputes both hashes.

## Migration Plan

1. Ship the migration that deletes `vault/memory-triggers/`.
2. The reconciler rewrites hooks on its first pass after upgrade.
3. Rollback is a downgrade of the binary; the deleted triggers come back from
   the vault history if needed (none were ever armed).

## Open Questions

None.
