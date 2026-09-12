# Feature Specification: Knowledge Layer

> 中文版: [spec.zh.md](./spec.zh.md)

**Created**: 2026-05-22 (as *Memory*) · **Merged with the Knowledge Base**: 2026-09-10 · **Reduced to plain files**: 2026-09-12
**Status**: Accepted
**Folder name**: this spec lives at `specs/knowledge/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on.

**Input**: Coffer holds one thing — **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is a **directory of Markdown files**. An agent finds what it needs by reading a catalogue and grepping, the way it navigates a codebase; a human finds it by opening a folder. There is **no derived index**: nothing is chunked, embedded or reconciled, so what one party writes the other sees immediately. See [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

## The principle this layer answers to

**Knowledge is managed by the human and the agent together.** Every decision below follows from it: metadata lives in the file rather than a database row because only the file is visible to both; the catalogue is generated rather than stored because a stored one would drift away from what the human sees in their file manager; the human's editor and the agent's `write` reach the same bytes with nothing in between.

## What was removed on 2026-09-12, and why

An audit of the live installation found most of this layer had never executed: `embedding_config` was an empty table, `.history/` did not exist on disk, 50 of 50 documents carried `converter: passthrough`, and every knowledge tool call in a month's history landed on the single day an agent built the corpus. Two structural mistakes explained it — properties had been built as directories (`notes/` ÷ `docs/`, `global` ÷ `project-<ULID>` ÷ collection), and once embeddings were never configured, an index bought only ranking that the agent does for itself.

Removed: any-format conversion and the converter registry; the `.raw/` lane; external source tracking; `source_mode` and the re-conversion lock; the lane split; cwd-derived scopes, auto-provisioning and `project-<ULID>` naming; FTS5, sqlite-vec, hybrid fusion, chunking, lazy reindex-on-read and explicit reindex; per-scope retrieval configuration; scope display labels. Eleven tables went with them.

## User Scenarios & Testing

### User Story 1 — One knowledge store, every agent (Priority: P1)

The developer works with Claude Code in the morning and Codex in the afternoon. In the morning an agent records that a service's login state is owned by `account.session`. In the afternoon a different agent finds it, because both read the same directory. No copy diverges, because there is only one copy.

**Independent Test**: from one MCP client write a fact; from a second client with a different agent identity, list the catalogue and read the file back.

### User Story 2 — Collections are the human's filing, and the unit of authorization (Priority: P1)

Some knowledge is a company's internal detail and must not reach every agent the developer runs; some is about a side project and may reach any of them. The developer creates a collection deliberately, puts the sensitive material in it, and authorizes only the agents that may see it. Inside a collection they nest folders however they like; Coffer neither knows nor cares.

**Independent Test**: create two collections, authorize one for a single agent, and confirm the other agent's catalogue and reads do not include it. Create a nested folder by hand and confirm the catalogue walks into it.

### User Story 3 — Find the right file without an index (Priority: P1)

An agent needs a fact it has no exact words for. It lists the collections, reads the one-line description of each, descends into the likely one, reads the titles and descriptions there, and either reads a file outright or greps for a literal string it now knows to look for.

**Independent Test**: with a populated collection, call the catalogue at each level and confirm titles and descriptions come back; grep a CJK string and confirm the matching file and line.

### User Story 4 — The human curates in their own tools (Priority: P2)

The developer drops a Markdown file into a collection from Finder, corrects a wrong line in their editor, and deletes one that went stale. Every change is live for the next agent call with no import step, because the file *is* the knowledge.

**Independent Test**: add a file out-of-band and confirm it appears in the catalogue and in grep; edit one and confirm the new bytes are what `read` returns.

### User Story 5 — The agent knows the layer exists (Priority: P1)

A skill Coffer delivers tells the agent this layer is here and how to work it. It arrives through the same channel that already delivers Coffer's other skills, so every managed agent gets it without a hook and without anything being written into the agent's own memory.

**Independent Test**: with a managed agent bound, confirm the knowledge skill is present in its skill directory and names the catalogue-then-grep motion.

### User Story 6 — Tidy, when the human asks for it (Priority: P3)

Notes accumulate and duplicate. The developer triggers a tidy pass that merges and rewrites them, having first archived every prior revision. They may also let it run on a timer, but only after switching it on.

**Independent Test**: run a tidy pass over a collection holding duplicates; confirm `.history/` holds the prior revisions and that the archived copies never appear in grep results.

## Acceptance Scenarios

### Scenario: a written note lands as a markdown file with a readable name

### Scenario: frontmatter carries title, description and actor

### Scenario: a file added out-of-band is visible to the next call

### Scenario: the catalogue lists collections with their README description

### Scenario: the catalogue lists one level of a collection

### Scenario: the catalogue walks into a nested directory

### Scenario: grep matches a literal string across a collection

### Scenario: grep matches CJK content

### Scenario: grep skips hidden directories

### Scenario: read returns a file by path

### Scenario: creating a collection registers a knowledge resource

### Scenario: an unknown collection is an error, never auto-created

### Scenario: a collection outside an agent's scope is absent from its catalogue

### Scenario: a collection outside an agent's scope cannot be read

### Scenario: write creates a file and replaces an existing one

### Scenario: delete removes the file from disk

### Scenario: a path escaping the knowledge root is rejected

### Scenario: the five built-in knowledge tools appear in the client tool list

### Scenario: tidy archives the prior revision before rewriting

### Scenario: tidy is a no-op when no internal model is configured

### Scenario: the tidy worker stays off unless enabled

### Scenario: the knowledge skill is delivered to a managed agent

### Scenario: the viewer renders content read-only and offers open and reveal

### Scenario: migration rewrites ULID documents into named files in collections

## Requirements

### Storage

- **FR-001**: Knowledge MUST be stored as Markdown files under `~/.coffer/knowledge/<collection>/`. The files are the **sole source of truth**; the system MUST NOT maintain any derived index of their content — no chunk table, no full-text index, no embeddings, and therefore no reconciliation of any kind.
- **FR-002**: A file's **path is its identity**. There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix.
- **FR-003**: Every file MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`, and nothing else. `description` is **required**, not optional: with no ranked index, the catalogue is the retrieval surface and a file that fails to describe itself is unfindable.
- **FR-004**: A collection MAY contain arbitrarily nested subdirectories. The system MUST NOT assign them meaning, MUST NOT require them, and MUST NOT create them.
- **FR-005**: Hidden entries (dot-prefixed) MUST be excluded from the catalogue and from grep. `.history/` is the only one the system itself writes.
- **FR-006**: Every name that becomes a path segment MUST pass a traversal guard, and path construction MUST live in exactly one module.

### Collections

- **FR-010**: A **collection** is a top-level subdirectory of the knowledge root and is one `knowledge` Resource. It MUST be created deliberately — through the REST/CLI/UI surface — and MUST NOT be provisioned by a read, a write, or an agent's working directory.
- **FR-011**: The system MUST NOT derive any boundary from the agent's cwd. There MUST be no `global` scope, no `project-<ULID>` naming, no git-root resolution and no scope-to-project-root mapping table.
- **FR-012**: A collection MUST support the Resource framework's **per-agent scope**: an agent sees, greps, reads and writes only the collections activated for it. An agent's calls MUST span **every** collection it is authorized for — there MUST be no rule that leaves an authorized collection out of a default.
- **FR-013**: A collection's one-line description MUST be the first paragraph of a `README.md` in its directory, absent when there is none. It MUST NOT be stored in the database.
- **FR-014**: Per-agent authorization is enforced at the MCP tool surface only, and the system MUST describe it as such: it prevents mistaken retrieval, not deliberate filesystem access.

### Retrieval

- **FR-020**: The catalogue MUST be **generated at call time** by walking the directory and reading frontmatter. The system MUST NOT materialize it to a file or a table.
- **FR-021**: `list` MUST walk **one level at a time**: with no path it returns every collection the caller may see, each with its README description and its file count; with a path it returns that directory's immediate subdirectories and files, each file with its `title` and `description`.
- **FR-022**: `grep` MUST run ripgrep over the files of the collections the caller may see, matching literally or by regex, recursively, and returning file, line number and matching line. Matches MUST be bounded and the response MUST flag truncation.
- **FR-023**: `read` MUST return a file's full text by path. There MUST be no chunking, no passage granularity and no `top_k`.
- **FR-024**: There MUST be **no `search` tool** and no retrieval mode anywhere on any surface.

### Writing

- **FR-030**: `write` MUST create a file from `title`, `description` and body text, or replace one when given an existing path. A write MUST be a plain file write — no LLM, no conversion, no indexing step.
- **FR-031**: `delete` MUST remove a file from disk.
- **FR-032**: The system MUST NOT accept uploads or convert any format. A human adds a document by placing a Markdown file in the directory; the filesystem is the ingestion surface.

### Tools and delivery

- **FR-040**: Coffer's MCP gateway MUST expose exactly **five** built-in knowledge tools under the `coffer__` prefix: `list`, `grep`, `read`, `write`, `delete`.
- **FR-041**: Built-in invocations MUST continue to record one `mcp_invocations` row (tool, actor, duration, outcome — no arguments, no content). A write or delete MUST additionally record an audit event with the agent as actor.
- **FR-042**: Coffer MUST deliver a **knowledge skill** through the existing skill-delivery channel (spec [skill-manager](../skill-manager/spec.md)), teaching the catalogue-then-grep motion. It MUST NOT install a hook, inject session context, or write into any agent's own memory files.

### Tidy

- **FR-050**: The system MUST provide a bounded agentic **tidy** pass over a collection, driven by the internal model connection, whose tool surface is the same five operations. It MUST copy a file's prior revision into `.history/` before any overwrite or merge. With no internal connection configured it MUST be a clean no-op.
- **FR-051**: Tidy MUST be triggerable by hand from the UI and from `coffer knowledge organize`. A background worker MAY run it on an interval, governed by one **installation-wide setting that is off by default**.
- **FR-052**: `.history/` MUST be dot-prefixed and therefore excluded from the catalogue and from grep.

### Surfaces

- **FR-060**: The REST API under `/api/v1/knowledge` and the `coffer knowledge` CLI group MUST cover: create a collection, list the catalogue at a path, read a file, write one, delete one, and trigger tidy. Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/knowledge/{name}`). There MUST be no upload, reindex, check-sources, update-source, embedding or per-scope settings endpoint.
- **FR-061**: The web UI MUST present the knowledge root as a **single tree** — no lane tabs — rendering content **read-only** through the unified file preview, with open-in-external-editor and reveal-in-file-manager on a file and its folder. There MUST be no in-app editor.
- **FR-062**: Read responses MUST carry the file's absolute path and its containing folder's absolute path.

### Migration

- **FR-070**: One migration MUST drop every knowledge-specific table — `documents`, `chunks`, the six `documents_fts*` tables, `embedding_config`, `knowledge_scope_labels`, `knowledge_scope_project_roots` — guarded so a database missing any of them still upgrades.
- **FR-071**: Before those tables are dropped, a data migration MUST rewrite the on-disk corpus: each document's `title` (held only in the database today) becomes its file name and its frontmatter, files move out of `notes/` and `docs/` into collections, and `.raw/` is deleted. Existing scopes land as two collections: `shopee` for the documents about internal systems and `coffer` for the project's own. The migration MUST be one-way, with **no compatibility shim left behind**.

### Constraints

- **FR-080**: No knowledge module may import an index, embedding or conversion library, and `sqlite-vec`, `fastembed`, mem0, chroma and LlamaIndex MUST NOT appear in the dependency set at all. `markitdown` stays, because inbound channel attachments still need extracting (spec [channels](../channels/spec.md) FR-030) — importlinter confines it to `infrastructure.chat`, its one consumer, so it cannot drift back into this layer.
- **FR-081**: The knowledge layer MUST NOT add any table to the database. A collection is a row in the kind-agnostic `resources` table like every other Resource.

## Success Criteria

- **SC-001**: A fact written by one agent is readable by a different agent through the catalogue, with no index step in between.
- **SC-002**: A file the human adds or edits outside Coffer is returned by the next call with no import, reindex or reconciliation.
- **SC-003**: An agent authorized for one collection cannot see another through any built-in tool.
- **SC-004**: The layer holds no knowledge-specific database table and no derived copy of any file's content.
- **SC-005**: A grep over the corpus returns matching file and line, including for CJK content, without a tokenizer.

## Assumptions

- The corpus stays small enough that a catalogue fits in an agent's context. At roughly 40 tokens an entry this is comfortable into the hundreds of files; the live corpus is 51. Past that the answer is a real semantic retrieval stack, built for that need — not the one removed here, which was never configured.
- Tidy rewrites files with no review step, so `.history/` is the whole safety net. It ships off by default for that reason.
