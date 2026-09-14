# Feature Specification: Knowledge Layer

> 中文版: [spec.zh.md](./spec.zh.md)

**Created**: 2026-05-22 (as *Memory*) · **Merged with the Knowledge Base**: 2026-09-10 · **Reduced to plain files**: 2026-09-12 · **Ingestion restored**: 2026-09-12 · **Ranked retrieval removed**: 2026-09-14
**Status**: Accepted
**Folder name**: this spec lives at `specs/knowledge/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on.

**Input**: Coffer holds **knowledge about the user's working environment**: their repositories, services, projects, the people they work with, the decisions and traps worth surviving a session. It is what the human uploads and what the human and an agent write together, filed into **collections**. It is a **directory of Markdown files** — the files are the sole truth, and a human finds what they need by opening a folder. An agent finds it by reading a catalogue, grepping a line, or asking which files a phrase appears in. See [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md).

**Knowledge is not memory.** Knowledge is about the world — a platform's API contract, a service's ownership, a document someone published — and it arrives because a person put it there. Memory is about the user and their projects, and it accrues on its own as agents work. They differ in every dimension that matters — who authors them, how they are partitioned, how they are delivered, and whether an entry can be *superseded* — so they are two layers: this one, filed by collection and **pulled** when needed, and spec [memory](../memory/spec.md), partitioned by project and **pushed** at session start.

## The principle this layer answers to

**Knowledge is managed by the human and the agent together.** Every decision below follows from it: metadata lives in the file rather than a database row because only the file is visible to both; the catalogue is generated rather than stored because a stored one would drift away from what the human sees in their file manager; the human's editor and the agent's `write` reach the same bytes with nothing in between.

## What was removed on 2026-09-12, and why

An audit of the live installation found most of this layer had never executed: `embedding_config` was an empty table, `.history/` did not exist on disk, 50 of 50 documents carried `converter: passthrough`, and every knowledge tool call in a month's history landed on the single day an agent built the corpus. Two structural mistakes explained it — properties had been built as directories (`notes/` ÷ `docs/`, `global` ÷ `project-<ULID>` ÷ collection), and once embeddings were never configured, an index bought only ranking that the agent does for itself.

Removed: any-format conversion and the converter registry; the `.raw/` lane; external source tracking; `source_mode` and the re-conversion lock; the lane split; cwd-derived scopes, auto-provisioning and `project-<ULID>` naming; FTS5, sqlite-vec, hybrid fusion, chunking, lazy reindex-on-read and explicit reindex; per-scope retrieval configuration; scope display labels. Eleven tables went with them.

## What came back on 2026-09-12, and why

One of those removals is reversed the same day, for a reason the removal did not weigh. This is not a reversal of the reduction — **path is still identity, frontmatter is still the metadata, and the files are still the sole truth**. What returns is an entrance.

**Ingestion returns because the filesystem is not reachable from where the user actually is.** "Put a Markdown file in the directory" is an entrance that exists only while the user is sitting at the machine. Their live entrance is a phone: a channel already accepts attachments and already extracts them for a turn (spec [channels](../channels/spec.md) FR-030). Sending a document to Coffer from that chat and having it land in a collection is the ingestion path this layer lacked — and it makes the Web upload worth having again as the same path's other end.

## What was removed on 2026-09-14, and why

Ranked retrieval was restored on 2026-09-12 and is now **taken out again, deliberately**. It worked: a query was embedded against the internal connection, section vectors were held in a disposable sidecar, cosine ranked them, and a literal search covered the case where no connection was configured. What went is the embedding half and everything that existed to serve it — the sidecar index, the freshness bookkeeping, the vector arithmetic, and the two ways an answer could be reached.

The reason is that the tier that was the *fallback* turned out to be the whole of what the corpus needed. At hundreds of files an agent that reads a catalogue and greps a phrase is already finding what it came for, and the ranking layer was buying that agent very little at the cost of a second thing to keep level with the disk, a dependency on a connection some installations do not have, and file text leaving the machine on a read. So `search` is now the literal search alone, promoted from fallback to the answer: ripgrep over the files the caller may see, reported a file at a time. Embeddings may earn their way back at a corpus size that needs them; that is a later decision, not a deferred piece of this one.

What the removal buys is that **nothing derived stands between a query and a file**. There is no index, so there is nothing to rebuild, nothing to be stale, nothing to reconcile, and nothing to exclude from a backup.

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

Notes accumulate and duplicate. The developer triggers a tidy pass that merges and rewrites them, having first archived every prior revision. They may also let it run on a timer, but only after switching it on — and, once the vault is synced, only on the one machine named as the tidy owner.

**Independent Test**: run a tidy pass over a collection holding duplicates; confirm `.history/` holds the prior revisions and that the archived copies never appear in grep results.

### User Story 7 — A document gets into the vault from wherever the user is (Priority: P1)

The developer is handed a PDF in a chat. They forward it to their Coffer channel, say which collection it belongs in, and it lands there as Markdown with its title and description filled in, the original kept aside. At the desk they do the same thing by dropping the file on the Knowledge page. Either way it is a file in a collection afterwards, indistinguishable from one they wrote by hand.

**Independent Test**: upload a non-Markdown document through the REST surface and confirm a Markdown file appears in the collection with frontmatter, the original under `.raw/`, and the converted text readable by `read`.

### User Story 8 — Get the file, not the line (Priority: P1)

An agent knows a distinctive word or phrase and wants the *files* it appears in — and it cannot afford to page through a catalogue first. It searches for that phrase and gets back the handful of files that contain it, each with its title, description and the lines that matched, so it can tell what it found before reading any of them. Matching is literal, so a question phrased in the agent's own words finds nothing; the tool's description and the delivered skill both say so.

**Independent Test**: write a file containing a distinctive phrase, search for it, and confirm the file comes back with its title, description and the matching line; search for wording that appears nowhere and confirm an empty result rather than an error.

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

### Scenario: the six built-in knowledge tools appear in the client tool list

### Scenario: search returns the files a phrase appears in, with the lines that matched

### Scenario: search spans only the collections the caller may see

### Scenario: an uploaded document lands as markdown with frontmatter

### Scenario: an uploaded original is kept under .raw/ and stays out of retrieval

### Scenario: an upload of an unsupported type is refused with its reason

### Scenario: a document forwarded to a channel lands in a collection

### Scenario: tidy archives the prior revision before rewriting

### Scenario: tidy is a no-op when no internal model is configured

### Scenario: the tidy worker stays off unless enabled

### Scenario: the knowledge skill is delivered to a managed agent

### Scenario: the viewer renders content read-only and offers open and reveal

### Scenario: migration rewrites ULID documents into named files in collections

## Requirements

### Storage

- **FR-001**: Knowledge MUST be stored as Markdown files under `~/.coffer/knowledge/<collection>/`. The files are the **sole source of truth**, and nothing derived may stand between a query and them: the system MUST NOT keep a retrieval index of any kind — no vectors, no sidecar, no cache — so every answer is read off disk at call time.
- **FR-002**: A file's **path is its identity**. There MUST be no separate id field in frontmatter and no id-to-path mapping anywhere. File names MUST be human-readable slugs derived from the title; a collision appends a short suffix.
- **FR-003**: Every file MUST carry YAML frontmatter with `title`, `description`, `actor` (`agent` | `user`), `created_at` and `updated_at`, and nothing else. `description` is **required**, not optional: search matches literally, so the catalogue is the retrieval surface for anything the caller cannot quote, and a file that fails to describe itself is unfindable.
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
- **FR-024**: `search` MUST answer a text query with the **files** the query appears in, each with its path, `title`, `description` and the lines that matched, bounded to a handful of files and a few matched lines each. It MUST use the same matcher `grep` uses — a regular expression, case-sensitive — over the same files; the two tools differ only in what they report, `grep` a line at a time and `search` a file at a time. There MUST be no score, no ranking, no heading, no retrieval *mode* on any surface and no second way an answer can be reached. Because matching is literal, `search` MUST say so where a caller reads it: the tool's own description MUST tell the agent to give it a distinctive word or exact phrase rather than a question in its own words.
- **FR-028**: A file MUST be searchable the instant it lands, with no reindex step — not because a freshness rule keeps an index level with the disk, but because there is no index to keep level. `search` reads the files themselves at call time, so a file written by an editor, a channel, `write` or `git` is found by the next call.
- **FR-029**: `search` MUST be confined to the files under the collections the caller may see and MUST skip hidden directories (`.history/`, `.raw/`). It MUST NOT send a file's content anywhere: search runs entirely on this machine and needs no connection of any kind.

### Writing and ingestion

- **FR-030**: `write` MUST create a file from `title`, `description` and body text, or replace one when given an existing path. A write MUST be a plain file write — no LLM, no conversion, no indexing step.
- **FR-031**: `delete` MUST remove a file from disk.
- **FR-032**: Placing a Markdown file in the directory MUST remain a complete way to add knowledge — no import, no registration, no conversion step. Ingestion below is an additional entrance for the cases where the filesystem is out of reach, never a required one.
- **FR-033**: The system MUST accept a document upload into a named collection and convert it to Markdown. Supported inputs MUST be exactly what `markitdown` handles plus plain text and CSV; an unsupported type MUST be refused with the type named, never stored half-converted.
- **FR-034**: A converted document MUST land as an ordinary Markdown file, indistinguishable afterwards from one written by hand: a readable slug for a name, and FR-003's frontmatter — `title` from the document (falling back to its file name) and `description` filled in, by the internal connection when one is configured and from the document's opening prose when not.
- **FR-035**: The uploaded original MUST be kept under a single hidden `.raw/` directory at the **collection's root**, at the converted file's path relative to that root, so a bad conversion can be redone from the bytes the user sent. `.raw/` MUST be excluded from the catalogue, from grep and from search, and MUST be removed when its converted file is deleted. Coffer MUST NOT re-convert it on a schedule or track it as an external source — the two mechanisms the 2026-09-12 reduction removed for never being used.
- **FR-036**: A document sent to a Coffer channel MUST be ingestible into a collection through the same conversion path, so the phone and the Knowledge page are two ends of one entrance (spec [channels](../channels/spec.md)). The channel MUST confirm the collection with the owner before storing, and MUST NOT store anything from a non-owner.
- **FR-037**: Upload MUST be bounded: one file per call, a size ceiling, and a refusal that names the limit. A conversion failure MUST leave neither a Markdown file nor a `.raw/` original behind.

### Tools and delivery

- **FR-040**: Coffer's MCP gateway MUST expose exactly **six** built-in knowledge tools under the `coffer__` prefix: `list`, `grep`, `read`, `search`, `write`, `delete`. Upload is not among them — a document enters through a human surface (the Knowledge page or a channel), not through an agent's tool call.
- **FR-041**: Built-in invocations MUST continue to record one `mcp_invocations` row (tool, actor, duration, outcome — no arguments, no content). A write or delete MUST additionally record an audit event with the agent as actor.
- **FR-042**: Coffer MUST deliver a **knowledge skill** through the existing skill-delivery channel (spec [skill-manager](../skill-manager/spec.md)), teaching the catalogue-then-grep motion and when to reach for `search` instead. This layer MUST NOT push anything into a session of its own accord and MUST NOT write into any agent's own memory files: knowledge is pulled. Session-start delivery belongs to spec [memory](../memory/spec.md), which carries its own budget and its own consent.

### Tidy

- **FR-050**: The system MUST provide a bounded agentic **tidy** pass over a collection, driven by the internal model connection, whose tool surface is the four file operations — `list`, `read`, `write`, `delete`. It MUST copy a file's prior revision into `.history/` before any overwrite or merge. With no internal connection configured it MUST be a clean no-op.
- **FR-051**: Tidy MUST be triggerable by hand from the UI and from `coffer knowledge organize`. A background worker MAY run it on an interval, governed by one **installation-wide setting that is off by default**. That setting MUST also **name a machine**. Today it is the single `auto_tidy_enabled` boolean on the singleton `internal_engine_config` row, which the worker's enabled-check reads on every tick; it MUST gain a companion owner-machine id — a `machine_id` from the sync machine registry (spec [vault-sync](../vault-sync/spec.md)), null until an owner is chosen — so the switch reads as *on, here* rather than merely *on*.
- **FR-052**: `.history/` MUST be dot-prefixed and therefore excluded from the catalogue and from grep.
- **FR-053**: The tidy setting MUST be **synced state**, travelling with the vault in the `internal-engine` document that already carries it, so every machine agrees on who the owner is. A pass MUST run only on the machine the setting names and MUST be a clean no-op on every other. Without that rule two machines rewrite one corpus independently: each merges the same pair of notes into a topic document, but into a *different* one, and git merges the result cleanly — both machines agree the originals are deleted, and the two topic documents are additions at different paths — so the vault ends up holding the same knowledge twice with nothing reported as a conflict. If the owner machine is off, no tidy happens at all, which is the accepted trade for a background nicety.
- **FR-054**: A tidy pass and a converge round MUST NOT overlap. Both write the vault, and an export taken mid-rewrite is a torn snapshot, so they MUST take the same lock. A pass MUST additionally be skipped while a conflict or a pending confirmation is outstanding, so a rewrite is never piled onto an unresolved divergence.
- **FR-055**: Where the owner's pass deleted a file that another machine edited, the **edit MUST win**: the file survives with its edit, the deletion is dropped, and the round MUST NOT report a conflict. A fresh edit is something a person or an agent just decided; the deletion is a housekeeping judgement the next pass will simply make again.

### Surfaces

- **FR-060**: The REST API under `/api/v1/knowledge` and the `coffer knowledge` CLI group MUST cover: create a collection, list the catalogue at a path, read a file, search, upload a document, write a file, delete one, and trigger tidy. Collection deletion goes through the Resource framework (`DELETE /api/v1/resources/knowledge/{name}`). There MUST be no index, reindex, check-sources, update-source, embedding-configuration or per-scope settings endpoint.
- **FR-061**: The web UI MUST present the knowledge root as a **single tree** — no lane tabs — rendering content **read-only** through the unified file preview, with open-in-external-editor and reveal-in-file-manager on a file and its folder. There MUST be no in-app editor. It MUST offer upload into the collection in view. There is nothing to report about index freshness and no rebuild to offer.
- **FR-062**: Read responses MUST carry the file's absolute path and its containing folder's absolute path.

### Migration

- **FR-070**: One migration MUST drop every knowledge-specific table — `documents`, `chunks`, the six `documents_fts*` tables, `embedding_config`, `knowledge_scope_labels`, `knowledge_scope_project_roots` — guarded so a database missing any of them still upgrades.
- **FR-071**: Before those tables are dropped, a data migration MUST rewrite the on-disk corpus: each document's `title` (held only in the database today) becomes its file name and its frontmatter, files move out of `notes/` and `docs/` into collections, and `.raw/` is deleted. Existing scopes land as two collections: `shopee` for the documents about internal systems and `coffer` for the project's own. The migration MUST be one-way, with **no compatibility shim left behind**.

### Constraints

- **FR-080**: This layer MUST carry **no vector-store or embedding-model dependency**: `sqlite-vec`, `fastembed`, mem0, chroma and LlamaIndex MUST NOT appear in the dependency set, and no vector may be computed, fetched or stored anywhere. Search is ripgrep, which the installation already has for `grep`. `markitdown` is this layer's converter as well as the channel's; the importlinter contract MUST admit exactly those two consumers and no others.
- **FR-081**: The knowledge layer MUST NOT add any table to `coffer.db`, and MUST NOT create a directory of its own outside the knowledge root. A collection is a row in the kind-agnostic `resources` table like every other Resource; everything else this layer holds is a file the human can open.

## Success Criteria

- **SC-001**: A fact written by one agent is readable by a different agent through the catalogue, with no index step in between.
- **SC-002**: A file the human adds or edits outside Coffer is returned by the next call with no import, reindex or reconciliation.
- **SC-003**: An agent authorized for one collection cannot see another through any built-in tool.
- **SC-004**: The layer holds no knowledge-specific table in `coffer.db` and keeps no derived copy of a file's content anywhere.
- **SC-005**: A grep over the corpus returns matching file and line, including for CJK content, without a tokenizer.
- **SC-006**: A file added out-of-band is returned by the next `search` with nothing rebuilt in between: the installation holds no index directory, no sidecar and no reindex command to find.
- **SC-007**: A document sent from a channel is a Markdown file in the intended collection afterwards, with its original recoverable, and the agent reads it the same way as any other file.
- **SC-008**: `search` works on a fresh installation with nothing configured at all — no connection, no index, no setting.

## Assumptions

- The corpus stays in the hundreds of files. The catalogue still fits an agent's context at that size and ripgrep over that many files is instant, so `search` is an addition to catalogue-then-grep rather than a replacement. Tens of thousands of files, or a corpus an agent genuinely cannot navigate by name, would be a different design and a different decision — and the place embeddings would be reconsidered.
- Tidy rewrites files with no review step, so `.history/` is the whole safety net. It ships off by default for that reason.
- The internal connection is the one place user content may leave the machine, exactly as spec [channels](../channels/spec.md) FR-022 already establishes for voice. Search never uses it — it reads no further than the disk — so the only knowledge text that goes there is what a tidy pass (FR-050) or an ingested document's generated description (FR-034) sends.
