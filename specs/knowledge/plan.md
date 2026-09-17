# Implementation Plan: Knowledge Layer

**Spec**: [./spec.md](./spec.md)
**ADR**: [Knowledge Is Plain Files](../../docs/decisions/knowledge-is-plain-files.md)
**Status**: Accepted

**Folder name**: this spec lives at `specs/knowledge/`, the spec id every
inbound link and `scripts/audit_acceptance.py` keys on.

## Summary

The knowledge layer is a **directory of Markdown files in two lanes**, not an
index over them. `~/.coffer/knowledge/<collection>/` holds `sources/`, written
by a person, an upload and `coffer__write`, and `topics/`, written only by the
curation pass that derives it from those sources. Sources are the truth; topics
are derived and rebuildable, which is what makes it safe for Coffer's own model
to rewrite them unattended. A **collection** is a top-level folder and one
`knowledge` Resource, created deliberately, and being a Resource is what gives
it a lifecycle, an audit trail and one `enabled` switch. It carries **no**
per-agent reach (FR-010).

**The agent does not retrieve through Coffer.** The gateway exposes exactly one
knowledge tool, `coffer__write`; `list`, `grep`, `read`, `search` and `delete`
are gone. An agent reads `topics/` with its own `Read` and `Grep`, at absolute
paths carried by a **generated skill** whose description names the subjects the
enabled collections cover and whose body is the whole catalogue. The skill is
written per agent — real bytes in each agent's own directory rather than a link
into one master — but its text is the same for every one of them: a disabled
collection appears in none of the copies, and an enabled one in all of them
(FR-010, FR-035).

One entrance exists beside the filesystem. A document — a PDF, a docx, a
spreadsheet — is uploaded from the Knowledge page or forwarded to a Coffer
channel, converted to Markdown, and lands in `sources/` with the original
visible beside it (FR-016…FR-019). It is an additional entrance and never a
required one: dropping a Markdown file into `sources/` is still a complete way
in.

What this layer does NOT hold — no index of any kind, no retrieval tool, no
cwd-derived scopes, no knowledge-specific table, no hidden directory — is a
standing constraint rather than a phase, and `spec.md`'s "What this layer is
not" carries it with the reasoning. The ADR carries the audit of the live
installation behind it.

## Technical Context

| Dimension | Value |
| --- | --- |
| **Language / Version** | Python 3.12+, TypeScript 5.x |
| **Primary dependencies added by this spec** | `PyYAML` (frontmatter); `ripgrep` on `PATH` (preferred, not required — there is a pure-Python fallback), now reached only from inside the process, to pick a pass's candidate documents (FR-023); `markitdown` for document conversion, whose only two consumers are this layer and the channel's media path, held there by an importlinter contract. The internal model connection, which curation and an uploaded document's generated description reach through the engine ports. No index or embedding library of any kind (FR-045). |
| **Storage** | Markdown files under `~/.coffer/knowledge/<collection>/{sources,topics}/`. **No database table** (FR-046): a collection is a row in the kind-agnostic `resources` table like every other Resource. |
| **Testing** | 4-tier model with acceptance markers. No fake embedding provider is needed, because nothing embeds; curation is tested through `AgenticCurationPort`, which is the only way this package reaches a model. |
| **Constraints** | Path construction confined to one module, which also owns the lane rule; hidden entries unaddressable; no module may import an index, embedding or conversion library; `application.knowledge` never imports langchain. |
| **Scale** | Single user; a corpus small enough that the catalogue of every topic document fits in a skill body — measured at ~5.2K tokens for 58 documents. |

## Constitution Check

Standard layer rules. The domain holds value objects that describe what is on
disk and nothing that describes a row; the application holds the service, the
one tool, the ingest service, the curation pass and the skill rendering and
delivery; infrastructure owns paths, the file tree, frontmatter, the ripgrep
adapter and the converters. PyYAML lives only in
`infrastructure/knowledge/frontmatter.py`, `markitdown` only in
`infrastructure/knowledge/converters/`, and path construction only in
`infrastructure/knowledge/paths.py`. The agentic loop is reached through
`AgenticCurationPort`, so langgraph stays inside `infrastructure.llm`.

## Project Structure

```text
backend/coffer/
├── domain/knowledge/
│   ├── entry.py                    # CollectionEntry (source_count + topic_count),
│   │                               # DirectoryEntry, FileEntry, CatalogueLevel,
│   │                               # KnowledgeFile (+ ingested_at), GrepMatch/Outcome
│   ├── converter.py                # the converter protocol + its value objects
│   ├── config.py                   # KnowledgeConfig — empty, forbids unknown keys
│   └── errors.py                   # CollectionNotFound / Exists, FileNotFound,
│                                   # UnsafeKnowledgePath (which also refuses a path
│                                   # outside a lane), UploadTooLarge,
│                                   # TopicReferencesFile, CurationBoundExceeded
├── application/knowledge/
│   ├── kind.py                     # make_knowledge_kind(); no per-agent reach
│   ├── service.py                  # the one service: collections, both lanes,
│   │                               # catalogue(), write_source, delete_source,
│   │                               # match_topics (internal candidate matching)
│   ├── builtin_tools.py            # the single MCP tool, `write`
│   ├── ingest.py                   # IngestService: convert, name, describe, keep
│   │                               # the original visible in sources/
│   ├── candidates.py               # distinctive_terms + select — which topic
│   │                               # documents one pass is shown in full
│   ├── curate.py                   # run_curation, CurationPass, AgenticCurationPort,
│   │                               # CURATION_SYSTEM — the bounded pass itself
│   ├── curate_tools.py             # its four tools: list_topics, read_topic,
│   │                               # write_topic, retire_topic. None reaches sources/
│   ├── curate_worker.py            # interval sweep, owner-machine gated, on by default
│   ├── skill_render.py             # pure text: description + catalogue body
│   └── skill_delivery.py           # writes each agent's own copy; removes a stale
│                                   # shared master rather than writing through it
├── infrastructure/knowledge/
│   ├── paths.py                    # the sole owner of path construction, the two
│   │                               # lane names, and the traversal guard
│   ├── fs.py                       # the file tree: lane walks, atomic read/write/
│   │                               # delete, write_original, the coffer_ingested_at
│   │                               # watermark and pending_sources
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
│   └── knowledge_tree_0085.py      # the two-lane rewrite 0085 runs before any DDL
└── surfaces/
    ├── http/knowledge/             # routes.py, schemas.py, dependencies.py,
    │                               # curation_state.py (the pass behind a setter, and
    │                               # the vault-write lock it shares with a converge
    │                               # round). The in-flight claim itself is the
    │                               # kind-agnostic UPKEEP_RUNS registry
    ├── http/knowledge_wiring.py    # composition: the service, ingest, the one tool,
    │                               # skill delivery, app.state.kinds["knowledge"]
    ├── http/curation_wiring.py     # the langgraph adapter, the switch read per tick,
    │                               # and the re-delivery a finished pass arms
    └── cli/knowledge_cmd.py        # `coffer knowledge …` — one module
```

There is no `frontend/src/kinds/` directory; a kind's React lives beside every
other kind's.

```text
frontend/src/
├── pages/KnowledgePage.tsx         # the collections list
├── pages/KnowledgeDetailPage.tsx   # the two lane trees, read-only preview, upload
│                                   # and the manual curation trigger
├── components/knowledge/           # KnowledgeTable + KnowledgeCreateDialog,
│                                   # KnowledgeTreeLevel (one level of one lane,
│                                   # matching the tree route), KnowledgePreviewBody
│                                   # (read-only, no in-app editor),
│                                   # KnowledgeFileDelete (sources only),
│                                   # KnowledgeUploadButton, KnowledgeWelcomePanel
├── lib/api/knowledge.ts            # the routes, with knowledgeTypes.ts beside it
└── lib/hooks/useKnowledge.ts       # every query + mutation, hierarchical keys under ["knowledge"]
```

## Surfaces

- **MCP — one tool**: `coffer__write`, into a named collection's `sources/`
  (FR-033). It takes no `scope`, no `path` and no lane: which lane a write lands
  in is not something a caller gets to choose. The session's agent identity is
  written in as an `agent` argument the schema does not advertise — it names the
  calling agent in the audit entry and narrows nothing, since the service
  refuses only a collection that does not exist or is disabled (FR-010). There
  is no `list`, `grep`, `read`, `search` or `delete` — an agent reads with its
  own tools, and deletion is a person's action.
- **HTTP — eight operations** under `/api/v1/knowledge`: `GET`/`POST
  /collections`, `GET /tree`, `GET`/`PUT`/`DELETE /file`, `POST /upload`, and
  `POST /collections/{name}/curate`. The lane is part of the path a `tree` call
  asks for, so the page asks twice rather than the route inventing a lane
  parameter. Deleting a collection goes through
  `DELETE /api/v1/resources/knowledge/{name}` — a collection's lifecycle is a
  Resource's. See [`contracts/api.openapi.yaml`](./contracts/api.openapi.yaml).
- **CLI — eight commands**: `collections`, `create`, `ls`, `read`, `write`,
  `delete`, `upload`, `curate`. There is deliberately no `grep` and no `search`:
  the corpus is plain Markdown at a path the group's help names, so a person's
  own `grep` is already better than anything this group could wrap.
- **UI**: two trees, read-only preview, delete on a source only, upload into the
  collection in view, a manual curation trigger, and open-in-editor and reveal on
  a file and its folder
  ([Daemon Proxies File Actions](../../docs/decisions/daemon-proxies-os-file-actions.md)).
- **Delivery**: a generated `coffer-knowledge` skill written as **real bytes into
  each registered agent's own `<config_dir>/skills/`** — not a skill-manager
  Resource, and not a symlink into one master, because its content differs by
  which collections that agent may see (FR-034, FR-035). It is re-rendered
  whenever the catalogue changes, and delivery never raises: a failure leaves the
  corpus readable at paths a person can still hand an agent. No hook, no session
  injection, no write into any agent's memory files.

## Curation

One bounded agentic pass over one collection, driven by the internal-engine
connection, whose tool surface is **four** operations — `list_topics`,
`read_topic`, `write_topic`, `retire_topic`. None of them can reach `sources/`,
which is the mechanical form of "sources are truth": the pass derives a second
copy from material it is not able to touch, so nothing it does can destroy
writing the user cannot get back. That is also why it replaces tidy rather than
renaming it. Tidy rewrote the only copy, so it shipped off and ran once; curation
ships **on**, because it is now the only path from a source to something an agent
can read.

The pass's context is bounded three ways (FR-023): the triggering source in full,
at most five candidate topic documents in full, and the collection's whole
catalogue of titles and descriptions. `candidates.py` picks the five by pulling
distinctive strings out of the source — backticked identifiers, dotted service
names, shouted constants, headings, CJK runs — and asking ripgrep which topic
documents contain them. That selection is allowed to be crude precisely because
the catalogue is in the prompt too: a model handed five irrelevant candidates and
every title can still conclude that none of them is the right home and open a new
document. Two rules are enforced rather than requested — at most eight writes per
pass (FR-025), and a write whose body names another knowledge file is refused
(FR-027), because a file name in prose is what produced 343 broken links. The
watermark is written last, so a pass that raises leaves `coffer_ingested_at`
unset and the material is curated by a later sweep rather than lost to one that
half-ran (FR-028).

`CurationWorker` is shaped like `RetentionWorker` — a catch-up sweep shortly
after boot, then on an interval, a failing pass logged without killing the
loop — and drains at most five passes per collection per sweep, so a freshly
migrated vault with dozens of pending sources fills in visibly rather than
waiting on one long batch. Every tick it asks `internal_engine_config` three
questions: is
`auto_curate_enabled` on (**default true**), does `curate_owner_machine_id` name
this machine (null means a single-machine vault, where here is the only answer),
and is a converge round waiting on the user (FR-031, FR-032). The pair is read
together so the switch means *on, here* rather than merely *on*: two machines
curating one corpus produce two different documents that git merges cleanly.
Only one pass per collection runs at a time, whoever asked — a manual trigger
arriving mid-pass is refused (`UPKEEP_ALREADY_RUNNING`, 409) and the sweep skips
that collection rather than waiting behind it (FR-030). A finished pass re-runs
skill delivery, because a topic document no catalogue names is one no agent can
find — and the worker re-delivers on **every** tick, outside the enabled check,
because a collection created, deleted, enabled or disabled changes what each
agent must be told even on a machine that is not the curation owner (FR-035).

## Migration

One revision, `0085_knowledge_two_lanes`, and **the order is the whole point**.
The on-disk rewrite runs first, before any DDL, so a failure anywhere in the
revision leaves the database exactly as it was — and before the rewrite moves a
single file it copies the whole knowledge root to a sibling directory named after
the revision and logs where (FR-043). Everything that exists today is a source:
nothing in the old tree was derived, because there was no pass to derive it, so
every content file moves into `sources/` with its nesting intact and `topics/` is
created empty. `.raw/` originals move into `sources/` as visible files rather
than being deleted — an uploaded PDF is the truest source there is, and the only
thing hiding it bought was keeping it out of an index that no longer exists.
`.history/` is deleted outright, with the reason it existed.

The same revision renames the three `internal_engine_config` columns to
`auto_curate_enabled` / `curate_owner_machine_id` / `curate_interval_s`, seeds
the switch on and the owner to this machine (FR-044), rewrites `knowledge_tidied`
audit rows to `knowledge_curated` — the event has a writer still, so the history
stays readable under the name the code now uses — and retires the shared
`coffer-knowledge` skill Resource, its bindings and its master folder, so no
agent is left holding a stale shared copy beside its generated one. `downgrade`
raises, and no compatibility shim is left behind anywhere. Details in
[`data-model.md`](./data-model.md).

## Risks and accepted trade-offs

| Risk | Position |
| --- | --- |
| **Curation is an unattended rewriter, and it is on by default.** Nothing diffs a pass's output before it lands. | `sources/` is the entire safety net, and unlike `.history/` it is a real one: nothing but a person writes there, so the material every topic is derived from survives any pass. Recovery is re-running curation, not reading back a revision. The eight-write bound and the one-pass-per-collection lock are what keep a bad pass small. |
| **`topics/` is empty until the first pass runs**, and stays empty where no internal connection is configured. | Accepted, and it is the reason the switch defaults on and the migration seeds it. The layer has acquired a hard dependency on the internal model that it did not have; a no-model pass reports `no_model` and leaves the watermark unset, so the corpus curates itself the day a connection is configured rather than staying dark. |
| **Whether a generated skill makes agents reach for the layer is still unproven.** A delivered skill describing the *layer* demonstrably did not: across 448 sessions it was never loaded. | The change is not "deliver a skill" but what the skill says — its description now names the corpus's subjects, which is the thing a model can match, and its body removes every guess by listing every document. Losing the read tools also loses the invocation record that would have measured it; the replacement is the agents' own transcripts, which Coffer already reads and which are retroactive. |
| **Per-agent skill copies must be reconciled.** A shared master needed one write; N agents need N. | Delivery is idempotent, re-armed by every catalogue change, and replaces a stale symlink rather than writing through it. A failure is logged per agent and never propagates: this must not be able to fail a boot or a pass. |
| **No semantic matching anywhere**, including in candidate selection. | Accepted, with a ceiling: it works while the catalogue fits in a skill body — ~5.2K tokens for 58 documents. Past that the answer is a real semantic stack built for that need, not the one removed here, which was never configured. |
| **Migration is destructive and one-way.** The lane agents read comes back empty, and a corpus the user wrote by hand returns in a machine's words. | Deliberate, and paid for with the backup taken before the first file moves. This is the cost the user accepted in exchange for the 343 broken references going away. |
| **Nothing here is a security boundary.** An agent with shell tools can read any file under the root. | Stated as such on every surface (FR-012): `enabled` decides what Coffer *delivers*, never what a process can open. Real isolation would need a separate vault or filesystem permissions, and is out of scope. The per-agent reach that once sat in front of this row is gone — an allow-list withholding a path from a reader who already has the root was an authorization in name only (FR-010). |

## Out of scope

- Any derived index: chunking, FTS5, vectors, embeddings, hybrid fusion,
  reindex, lazy reindex-on-read.
- Any retrieval tool. Reading, listing, grepping and searching are the agent's
  own, at the absolute paths the delivered skill carries (FR-033).
- Re-converting an ingested original on a schedule, tracking it as an external
  source, or locking it against edits. The original is kept, visibly, in
  `sources/` so a bad conversion can be redone by hand (FR-016) and for nothing
  else.
- Any derived boundary: cwd-resolved scopes, auto-provisioning,
  `project-<ULID>` naming, git-root resolution.
- A review step before a pass's writes land, or an archive of what one replaced.
  Both are answered by `sources/` being untouched.
- An in-app editor. The UI renders; the user's own editor edits.
- Reranking, HyDE, multi-query or LLM synthesis at read time — the agent
  synthesizes.
- A filesystem watcher. The sweep compares each source's modification time with
  its own watermark, which needs nothing resident.
- Converging the corpus across machines. The knowledge files do travel — spec
  [vault-sync](../vault-sync/spec.md) converges the vault bidirectionally with a
  git remote the user owns — but nothing in this layer knows about it. What this
  layer owes that mechanism is one rule: an unattended rewriter runs on exactly
  one machine (FR-032), because two machines merging the same sources produce two
  different topic documents that git merges cleanly.
