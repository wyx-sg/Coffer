# Implementation Plan: Knowledge Layer

**Spec**: [./spec.md](./spec.md)
**ADR**: [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)
**Status**: Accepted

**Folder name**: this spec lives at `specs/knowledge/`, the spec id every
inbound link and `scripts/audit_acceptance.py` keys on.

## Summary

The knowledge layer is a **directory of Markdown files**, not an index over
them. `~/.coffer/knowledge/<collection>/` is **one tree of documents** that
people and Coffer's own model write together: a person edits any document in
their own editor, and the curation pass rewrites documents as it merges new
knowledge in. New knowledge — `coffer__write`, `coffer knowledge write`, an
upload, a channel `/save` — arrives as **material** in the collection's hidden
`.inbox/`, and a pass folds what is new in it into the documents and deletes
the item. A person's edit to a document is carried by the next pass into the
rest of the collection and never reverted. A **collection** is a top-level folder and one
`knowledge` Resource, created deliberately, and being a Resource is what gives
it a lifecycle, an audit trail and one `enabled` switch. It carries **no**
per-agent reach (FR-010).

**The agent does not retrieve through Coffer.** The gateway exposes exactly one
knowledge tool, `coffer__write`; `list`, `grep`, `read`, `search` and `delete`
are gone. An agent reads the documents with its own `Read` and `Grep`, at absolute
paths carried by **Coffer's own generated skill**, `coffer-guide`, whose
description names the subjects the enabled collections cover and whose body is
Coffer's manual followed by the whole catalogue. That skill is an ordinary
`skill` Resource — one master folder, one row, one link per agent — so this
layer renders its text and the skill kind does the writing and the delivering.
One rendering serves every agent: a disabled collection appears in none of what
an agent reads, and an enabled one in all of it (FR-010, FR-034, FR-035).

One entrance exists beside the filesystem. A document — a PDF, a docx, a
spreadsheet — is uploaded from the Knowledge page or forwarded to a Coffer
channel, converted to Markdown, and submitted as material; neither the original
nor the extracted file is kept, because what the collection holds is the
knowledge, merged (FR-016…FR-019). It is an additional entrance and never a
required one: writing or editing a Markdown document in the tree is still a
complete way in.

What this layer does NOT hold — no index of any kind, no retrieval tool, no
cwd-derived scopes, no knowledge-specific table, no hidden directory but the
inbox — is a
standing constraint rather than a phase, and `spec.md`'s "What this layer is
not" carries it with the reasoning. The ADR carries the audit of the live
installation behind it.

## Technical Context

| Dimension | Value |
| --- | --- |
| **Language / Version** | Python 3.12+, TypeScript 5.x |
| **Primary dependencies added by this spec** | `PyYAML` (frontmatter); `ripgrep` on `PATH` (preferred, not required — there is a pure-Python fallback), now reached only from inside the process, to pick a pass's candidate documents (FR-023); `markitdown` for document conversion, whose only two consumers are this layer and the channel's media path, held there by an importlinter contract. The internal model connection, which curation and an uploaded document's generated description reach through the engine ports. No index or embedding library of any kind (FR-045). |
| **Storage** | Markdown files under `~/.coffer/knowledge/<collection>/`, one tree per collection plus a hidden `.inbox/`. **No database table** (FR-046): a collection is a row in the kind-agnostic `resources` table like every other Resource. |
| **Testing** | 4-tier model with acceptance markers. No fake embedding provider is needed, because nothing embeds; curation is tested through `AgenticCurationPort`, which is the only way this package reaches a model. |
| **Constraints** | Path construction confined to one module, which also owns the inbox name and the rule that a document lives inside a collection and is not its README; hidden entries unaddressable; no module may import an index, embedding or conversion library; `application.knowledge` never imports langchain. |
| **Scale** | Single user; a corpus small enough that the catalogue of every document fits in a skill body — measured at ~5.2K tokens for 58 documents. |

## Constitution Check

Standard layer rules. The domain holds value objects that describe what is on
disk and nothing that describes a row; the application holds the service, the
one tool, the ingest service, the curation pass and the guide skill's text —
rendering only, since the writing belongs to the skill kind; infrastructure owns paths, the file tree, frontmatter, the ripgrep
adapter and the converters. PyYAML lives only in
`infrastructure/knowledge/frontmatter.py`, `markitdown` only in
`infrastructure/knowledge/converters/`, and path construction only in
`infrastructure/knowledge/paths.py`. The agentic loop is reached through
`AgenticCurationPort`, so langgraph stays inside `infrastructure.llm`.

## Project Structure

```text
backend/coffer/
├── domain/knowledge/
│   ├── entry.py                    # CollectionEntry (document_count + pending_count),
│   │                               # DirectoryEntry, FileEntry, CatalogueLevel,
│   │                               # KnowledgeFile (+ curated_at), Pending,
│   │                               # GrepMatch/Outcome
│   ├── converter.py                # the converter protocol + its value objects
│   ├── config.py                   # KnowledgeConfig — empty, forbids unknown keys
│   └── errors.py                   # CollectionNotFound / Exists, FileNotFound,
│                                   # UnsafeKnowledgePath (which also refuses a path
│                                   # that cannot name a document), UploadTooLarge,
│                                   # TopicReferencesFile, CurationBoundExceeded
├── application/knowledge/
│   ├── kind.py                     # make_knowledge_kind(); no per-agent reach
│   ├── service.py                  # the one service: collections, catalogue(),
│   │                               # submit (material → inbox, or promoted with no
│   │                               # model), delete_document, match_documents
│   │                               # (internal candidate matching)
│   ├── builtin_tools.py            # the single MCP tool, `write`
│   ├── ingest.py                   # IngestService: convert, describe, submit as
│   │                               # material; keeps neither file
│   ├── candidates.py               # distinctive_terms + select — which
│   │                               # documents one pass is shown in full
│   ├── curate.py                   # run_curation, CurationPass, AgenticCurationPort,
│   │                               # CURATION_SYSTEM, pending_items — the bounded
│   │                               # pass itself, one item (material or an edit) each
│   ├── curate_tools.py             # its four tools: list_documents, read_document,
│   │                               # write_document, retire_document. None reaches
│   │                               # the inbox, the README or another collection
│   ├── curate_worker.py            # interval sweep, owner-machine gated, on by default
│   ├── guide_render.py             # pure text: the `coffer-guide` SKILL.md —
│   │                               # description + manual + catalogue body. Its
│   │                               # output must be byte-identical across machines
│   └── skill_assets/               # coffer-guide.md, the hand-written half of the
│                                   # body, shipped as package data
├── infrastructure/knowledge/
│   ├── paths.py                    # the sole owner of path construction, the inbox
│   │                               # name, require_document, and the traversal guard
│   ├── fs.py                       # the file tree: atomic read/write/delete, the
│   │                               # inbox (submit_material, inbox_items, promote,
│   │                               # discard_material), the coffer_curated_at stamp
│   │                               # (mark_curated) and edited_documents
│   ├── frontmatter.py              # the only PyYAML importer
│   ├── naming.py                   # slugify + unique_name — the path is the identity
│   ├── grep.py                     # ripgrep, with the pure-Python fallback in
│   ├── grep_fallback.py            #   grep_fallback.py, for a machine that lacks it
│   └── converters/                 # registry.py picks one by type: markitdown_converter.py,
│                                   # csv_converter.py, passthrough_converter.py — the only
│                                   # place `markitdown` is imported
├── infrastructure/persistence/migrations/
│   ├── knowledge_tree_0066.py      # the 0066 rewrite, frozen where it was left
│   ├── knowledge_tree_0066_text.py #   with the helpers it froze alongside it
│   ├── knowledge_tree_0085.py      # the two-lane rewrite 0085 ran before any DDL
│   └── knowledge_tree_0101.py      # the one-tree rewrite: both lanes queued in .inbox/
└── surfaces/
    ├── http/knowledge/             # routes.py, schemas.py, dependencies.py,
    │                               # curation_state.py (the pass behind a setter, and
    │                               # the vault-write lock it shares with a converge
    │                               # round). The in-flight claim itself is the
    │                               # kind-agnostic UPKEEP_RUNS registry
    ├── http/knowledge_wiring.py    # composition: the service, ingest, the one tool,
    │                               # app.state.kinds["knowledge"]
    ├── http/guide_wiring.py        # the one place the renderer above and the skill
    │                               # kind's BuiltinSkillSeed are joined — the two
    │                               # kinds may not import each other. Run at boot
    │                               # and after every curation pass
    ├── http/curation_wiring.py     # the langgraph adapter, the switch read per tick,
    │                               # and the guide refresh a finished pass arms
    └── cli/knowledge_cmd.py        # `coffer knowledge …` — one module
```

There is no `frontend/src/kinds/` directory; a kind's React lives beside every
other kind's.

```text
frontend/src/
├── pages/KnowledgePage.tsx         # the collections list
├── pages/KnowledgeDetailPage.tsx   # one tree, read-only preview, upload and the
│                                   # manual curation trigger
├── components/knowledge/           # KnowledgeTable + KnowledgeCreateDialog,
│                                   # KnowledgeTreeLevel (one level of the tree,
│                                   # matching the tree route), KnowledgePreviewBody
│                                   # (read-only, no in-app editor),
│                                   # KnowledgeFileDelete (any document),
│                                   # KnowledgeUploadButton, KnowledgeWelcomePanel
├── lib/api/knowledge.ts            # the routes, with knowledgeTypes.ts beside it
└── lib/hooks/useKnowledge.ts       # every query + mutation, hierarchical keys under ["knowledge"]
```

## Surfaces

- **MCP — one tool**: `coffer__write`, which submits material to a named
  collection's inbox (FR-033). It takes no `scope`, no `path` and no folder:
  where the knowledge belongs is curation's decision, and the answer says
  `pending`, or `written` with a document path when no model is configured. The session's agent identity is
  written in as an `agent` argument the schema does not advertise — it names the
  calling agent in the audit entry and narrows nothing, since the service
  refuses only a collection that does not exist or is disabled (FR-010). There
  is no `list`, `grep`, `read`, `search` or `delete` — an agent reads with its
  own tools, and deletion is a person's action.
- **HTTP — eight operations** under `/api/v1/knowledge`: `GET`/`POST
  /collections`, `GET /tree`, `GET`/`DELETE /file`, `POST /material`,
  `POST /upload`, and `POST /collections/{uid}/curate`. There is no
  write-a-document route: a person edits a document in their own editor, and
  every other entrance submits material. Deleting a collection goes through
  `DELETE /api/v1/resources/{uid}` — a collection's lifecycle is a
  Resource's. See [`contracts/api.openapi.yaml`](./contracts/api.openapi.yaml).
- **CLI — eight commands**: `collections`, `create`, `ls`, `read`, `write`,
  `delete`, `upload`, `curate`. There is deliberately no `grep` and no `search`:
  the corpus is plain Markdown at a path the group's help names, so a person's
  own `grep` is already better than anything this group could wrap.
- **UI**: one tree, a pending count, read-only preview, delete on any document, upload into the
  collection in view, a manual curation trigger, and open-in-editor and reveal on
  a file and its folder
  ([Daemon Proxies File Actions](../../docs/decisions/daemon-proxies-os-file-actions.md)).
- **Delivery**: the catalogue rides Coffer's own `coffer-guide` skill, which is an
  ordinary `skill` Resource — one master folder under `~/.coffer/skills/`, one
  row, one link per agent, delivered by spec skill-manager's own predicate and
  machinery (FR-034, FR-035). This layer renders the text (`guide_render.py`);
  `application/skill/builtin_seed.py` writes it, and `surfaces/http/guide_wiring.py`
  is the one place the two are joined. It is re-rendered
  whenever the catalogue changes, and a render or write that fails never raises:
  the previous master stays exactly where it was, and the
  corpus stays readable at paths a person can still hand an agent. No hook, no session
  injection, no write into any agent's memory files.

## Curation

One bounded agentic pass over one collection, driven by the internal-engine
connection, whose tool surface is **four** operations — `list_documents`,
`read_document`, `write_document`, `retire_document` — fenced to that
collection's documents: none of them can reach the inbox, the README or another
collection (FR-021). A pass takes **one item**: either inbox material, which it
merges into whichever document owns the subject (or a new one when none does),
or a document someone edited since curation last stamped it, whose edit it
carries outward into the documents that disagree with it. The instructions make
two rules explicit because no code can adjudicate them (FR-026): where new
material contradicts a document the newer statement wins and the superseded one
stays legible as a dated correction, and a person's edit is deliberate — the
pass never reverts or rewords it.

The pass's context is bounded three ways (FR-023): the item in full, at most
five candidate documents in full, and the collection's whole catalogue of titles
and descriptions. `candidates.py` picks the five by pulling distinctive strings
out of the item — backticked identifiers, dotted service names, shouted
constants, headings, CJK runs — and asking ripgrep which documents contain them.
That selection is allowed to be crude precisely because the catalogue is in the
prompt too: a model handed five irrelevant candidates and every title can still
conclude that none of them is the right home and open a new document. Two rules
are enforced rather than requested — at most eight writes per pass (FR-025), and
a write whose body names another knowledge file is refused (FR-027), because a
file name in prose is what produced 343 broken links. The item is settled last
(FR-028): material is deleted from the inbox, or an edited document stamped with
`coffer_curated_at`, only after the loop returns, so a pass that raises leaves
the item where it was and a later sweep retries it. Curation's own writes are
stamped as they land, with the file's mtime set to the stamp, so the sweep never
hands a pass its own output back.

With no internal connection there is nothing to merge with, and material does
not wait for one (FR-029): `KnowledgeService.submit` promotes a submission to a
document of its own on the spot, and a pass run without a model promotes
whatever is left in the inbox and reports `no_model` with the paths it promoted.

`CurationWorker` is shaped like `RetentionWorker` — a catch-up sweep shortly
after boot, then on an interval (60 s by default, re-read every sweep), a
failing pass logged without killing the loop. Each sweep asks
`pending_items` what a collection owes — inbox material first, oldest first,
then documents whose mtime is newer than their stamp — and runs at most five
passes per collection, so a freshly migrated vault with dozens of queued items
fills in visibly rather than waiting on one long batch. Every tick it asks
`internal_engine_config` three questions: is `auto_curate_enabled` on
(**default true**), does `curate_owner_machine_id` name this machine (null means
a single-machine vault, where here is the only answer), and is a converge round
waiting on the user (FR-031, FR-032). The pair is read together so the switch
means *on, here* rather than merely *on*: two machines curating one corpus
produce two different documents that git merges cleanly. Only one pass per
collection runs at a time, whoever asked — a manual trigger arriving mid-pass is
refused (`UPKEEP_ALREADY_RUNNING`, 409) and the sweep skips that collection
rather than waiting behind it (FR-030). A pass that wrote or promoted anything
refreshes the guide skill, because a document no catalogue names is one no agent
can find — and the worker refreshes on **every** tick, outside the enabled
check, because a collection created, deleted, enabled or disabled changes what
every agent must be told even on a machine that is not the curation owner
(FR-035).

## Migration

The current shape is revision `0101_knowledge_one_tree`, which rewrites the
disk and nothing else. Before a single file moves it copies the whole knowledge
root to `<root>.pre-0101.bak` and logs where (FR-043); a second run reuses that
backup. It then queues every Markdown file of both lanes in the collection's
`.inbox/` — `topics/` first, because those documents are already organised by
subject, then `sources/` in the order they were last modified — with flat names
that say where each came from and mtimes spaced a second apart so the sweep
drains them in that order. Non-Markdown originals are dropped (they survive only
in the backup), both lanes are removed, and `README.md` stays at the collection
root. The sweep then re-distils the whole corpus into one tree. Nothing in the
database changes, `downgrade` puts nothing back, and the backup is the way back,
by hand (FR-042).

It runs on top of revision `0085_knowledge_two_lanes`, which introduced the
lanes. **There the order was the whole point**: the on-disk rewrite ran first,
before any DDL, so a failure anywhere in the revision left the database exactly
as it was, and it backed the root up before moving a file. It moved every
content file into `sources/`, created `topics/` empty, turned `.raw/` originals
into visible files in `sources/`, and deleted `.history/`.

The same revision renamed the three `internal_engine_config` columns to
`auto_curate_enabled` / `curate_owner_machine_id` / `curate_interval_s`, seeded
the switch on and the owner to this machine (FR-044), rewrote `knowledge_tidied`
audit rows to `knowledge_curated` — the event has a writer still, so the history
stays readable under the name the code now uses — and retired the shared
`coffer-knowledge` skill Resource, its bindings and its master folder, so no
agent was left holding a stale shared copy beside the per-agent one that
delivery then wrote. A later migration finished the job: with the catalogue
moved into `coffer-guide`, it sweeps each registered agent's own skill directory
and removes what that per-agent delivery left, recognising Coffer's own by the
symlink or the `SKILL.md`/`README.md` pair it always wrote and leaving anything
else alone (FR-034). No compatibility shim is left behind anywhere. Details in
[`data-model.md`](./data-model.md).

## Risks and accepted trade-offs

| Risk | Position |
| --- | --- |
| **Curation is an unattended rewriter of the documents people also edit, and it is on by default.** Nothing diffs a pass's output before it lands, and there is no untouched copy of the material behind it any more. | Accepted as the price of co-writing: a collection is edited by people and the model together, so there is no lane the model cannot reach. What keeps a bad pass small is the eight-write bound, one item per pass and the one-pass-per-collection lock; what keeps it from undoing a person is the instruction that a person's edit stands, plus the stamp that makes an edit the thing a pass is handed rather than something it overwrites unseen. Where vault sync is configured, the vault's git history (spec vault-sync) is the record of what a pass replaced. |
| **A new collection is empty until material is merged**, and material waits in the hidden inbox while a pass is pending. | The inbox is counted on the collection list (`pending_count`) so the wait is visible, the sweep runs every minute by default, and with no internal connection configured nothing waits at all: material is promoted to a document as it stands. |
| **Whether a generated skill makes agents reach for the layer is still unproven.** A delivered skill describing the *layer* demonstrably did not: across 448 sessions it was never loaded. | The change is not "deliver a skill" but what the skill says — its description now names the corpus's subjects, which is the thing a model can match, and its body removes every guess by listing every document. Losing the read tools also loses the invocation record that would have measured it; the replacement is the agents' own transcripts, which Coffer already reads and which are retroactive. |
| **The catalogue now lives in a skill this layer does not own.** Its text is rendered here and written, delivered and reclaimed by the skill kind, across a boundary the two kinds may not import across. | The join is one composition-root module and the seam is a string of Markdown, so neither kind learns about the other. The seed is idempotent — an unchanged catalogue writes nothing — and a failure at either end is logged and swallowed: this must not be able to fail a boot or a pass. |
| **The rendered skill is different on every machine, and cannot not be.** It is rendered from the enabled collections, and `enabled` is machine-local reach — so two machines with the same files render different text, and while both halves of a skill converged they overwrote each other every round, forever. | The artifact does not converge at all (spec [vault-sync](../vault-sync/spec.md) FR-093): the `skill` kind declares its own generated row derived, and the mirrored `skills/` tree leaves that folder alone in both directions. Determinism stays as a rule with a smaller job (FR-047) — same build, same catalogue, same bytes — so an unchanged boot writes, audits and delivers nothing. |
| **No semantic matching anywhere**, including in candidate selection. | Accepted, with a ceiling: it works while the catalogue fits in a skill body — ~5.2K tokens for 58 documents. Past that the answer is a real semantic stack built for that need, not the one removed here, which was never configured. |
| **Migration 0101 is destructive and one-way.** Every document goes back through the inbox and returns in a machine's words, and uploaded originals are dropped. | Deliberate, and paid for with the backup taken before the first file moves. The user asked for the corpus to be distilled again into one co-edited tree; the originals and the old lanes remain in `<root>.pre-0101.bak`. |
| **Nothing here is a security boundary.** An agent with shell tools can read any file under the root. | Stated as such on every surface (FR-012): `enabled` decides what Coffer *delivers*, never what a process can open. Real isolation would need a separate vault or filesystem permissions, and is out of scope. The per-agent reach that once sat in front of this row is gone — an allow-list withholding a path from a reader who already has the root was an authorization in name only (FR-010). |

## Out of scope

- Any derived index: chunking, FTS5, vectors, embeddings, hybrid fusion,
  reindex, lazy reindex-on-read.
- Any retrieval tool. Reading, listing, grepping and searching are the agent's
  own, at the absolute paths the delivered skill carries (FR-033).
- Keeping an upload's original, re-converting it, or tracking it as an external
  source. An upload is a carrier for knowledge: its text is submitted as
  material and merged, and the file itself is not kept (FR-016).
- Any derived boundary: cwd-resolved scopes, auto-provisioning,
  `project-<ULID>` naming, git-root resolution.
- A review step before a pass's writes land, or an archive of what one replaced
  beyond the vault's own git history.
- An in-app editor. The UI renders; the user's own editor edits.
- An agent-facing delete. Deleting a document is a person's action (FR-020).
- Reranking, HyDE, multi-query or LLM synthesis at read time — the agent
  synthesizes.
- A filesystem watcher. The sweep lists the inbox and compares each document's
  modification time with its own stamp, which needs nothing resident.
- Converging the corpus across machines. The knowledge files do travel — spec
  [vault-sync](../vault-sync/spec.md) converges the vault bidirectionally with a
  git remote the user owns — but nothing in this layer knows about it. What this
  layer owes that mechanism is one rule: an unattended rewriter runs on exactly
  one machine (FR-032), because two machines merging the same material produce
  two different documents that git merges cleanly.
