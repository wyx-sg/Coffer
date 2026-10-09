# Knowledge structures: how other products organise agent knowledge

**Feature**: how a knowledge base for coding agents is *structured* — kept raw sources versus compiled wiki pages, page types and links, generated versus hand-kept indexes, ingest and lint operations — and how products present version history, change logs and sources in their UI · **Coffer spec**: [knowledge](../../openspec/specs/knowledge/spec.md) · **Related ADRs**: [Knowledge Is a Wiki of Pages Compiled From Kept Sources](../decisions/knowledge-is-a-wiki-of-pages-compiled-from-kept-sources.md), [Knowledge Is Plain Files](../decisions/knowledge-is-plain-files.md)
**Researched**: 2026-10 · **Method**: web research, primary sources (repos, official docs, engineering blogs, papers); star counts from repository pages on 2026-10-09. `[P]` marks a claim checked against a primary source, `[S]` one taken from a secondary source, `[V]`/`[K]` in part 3 a UI checked against its page versus recalled. It extends [Knowledge curation](./knowledge-curation.md) (2026-09), which covers Karpathy's gist, DeepWiki, Obsidian, Basic Memory, Mem, Notion AI, Cognee, Khoj, AnythingLLM and hosted assistants.

The note has three parts: open-source implementations of the "LLM Wiki" pattern; how coding agents, memory frameworks and AI knowledge apps structure knowledge and retrieve it; and how document tools present history, change logs and sources.

---

## Part 1. LLM Wiki implementations
### Summary table

| Project | Stars | Kind | Raw / pages layout | Link style | index.md | log | Ingest trigger |
|---|---|---|---|---|---|---|---|
| tobi/qmd | 30.3k | Search engine (BM25 + vector + rerank, MCP) | n/a, indexes any md "collections" | n/a | n/a | n/a | `qmd embed` / reindex |
| nashsu/llm_wiki | 17.5k | Tauri desktop app | `raw/sources/` (immutable), `raw/assets/`, `wiki/` + `purpose.md`, `schema.md`, `.llm-wiki/` | `[[wikilink]]` | LLM-updated each ingest; deterministic "rebuild index" exists | `wiki/log.md` LLM-written | Persistent queue, folder watcher on `raw/sources/`, web clipper |
| AgriciDaniel/claude-obsidian | 15.0k | Claude Code plugin (15 skills) + Python core | `inbox/` (staging), `.raw/` (immutable, content-addressed), `wiki/`, `.vault-meta/` | Obsidian wikilinks + md links | Updated inside the ingest transaction | log + "fold" rollups; git checkpoint opt-in | Manual `/wiki-ingest` |
| Ar9av/obsidian-wiki | 3.5k | 39 agent skills + Python CLI | `_raw/` (staging), `concepts/ entities/ skills/ references/ synthesis/ journal/ projects/`, `_staging/`, `_archives/` | `[[wikilinks]]` | Written via a locked CLI (`memory sync`) | `log.md` + generated `hot.md` | Manual skill + SessionStart/Stop hooks |
| atomicstrata/llm-wiki-compiler (`llmwiki`, formerly atomicmemory) | 2.2k | TS CLI/SDK/MCP compiler | `sources/`, `wiki/concepts/`, `wiki/queries/`, `wiki/<entity>/`, `.llmwiki/state.json` | `[[slug\|Title]]` + `aliases:` | Generated after every compile | Root `log.md`, appended by tool | `llmwiki ingest` then `compile` (incremental by hash) |
| lucasastorian/llmwiki | 1.6k | Next.js app + MCP server | User folder untouched; adds `wiki/` + `.llmwiki/index.db` | Cross-links + footnote citations | `overview.md` (no log; legacy log.md protected) | none (git optional) | Watcher indexes; nightly Claude Routine does synthesis |
| Astro-Han/karpathy-llm-wiki | 1.6k | Single Agent Skill | `raw/<topic>/YYYY-MM-DD-slug.md`, `wiki/<topic>/<article>.md` (one level) | Relative markdown links | LLM-maintained, lint auto-fixes | LLM-appended `wiki/log.md` | Manual "ingest this" |
| ussumant/llm-wiki-compiler | 325 | Claude Code / Codex plugin | Sources anywhere; `wiki/INDEX.md`, `topics/`, `concepts/`, `schema.md` | wikilinks/backlinks | LLM | n/a | `/wiki-compile` batch, `/wiki-ingest` single |
| kfchou/wiki-skills | 185 | Claude Code plugin | `raw/`, `wiki/pages/` (flat, slug-named), `SCHEMA.md`, `bin/` | `[[slug]]` | **Generated** from frontmatter, gitignored | **git history** (`Wiki-Op:` trailer); log.md only for non-git | Manual skills |
| NousResearch Hermes bundled `llm-wiki` skill | (bundled in Hermes Agent) | Skill | `raw/{articles,papers,transcripts,assets}`, `entities/ concepts/ comparisons/ queries/`, `_archive/`, `_meta/` | `[[wikilinks]]`, ≥2 outbound | LLM, split >50 entries, topic map >200 | `log.md`, rotated at 500 entries | Manual |
| Google OKF v0.2 spec (GoogleCloudPlatform/knowledge-catalog) | — | Exchange format | Any directory tree; reserved `index.md`/`log.md` at any level | **Standard md links, bundle-absolute `/x/y.md` recommended** | Optional, may be generated | Optional, `## YYYY-MM-DD` | n/a |

---

### 1. nashsu/llm_wiki (17.5k stars, 171 open issues)
https://github.com/nashsu/llm_wiki

- **Layout**
  ```
  purpose.md   schema.md
  raw/sources/ (immutable)   raw/assets/
  wiki/ index.md log.md overview.md + entity/concept/source pages, wiki/queries/, wiki/media
  .llm-wiki/ (config, chats/{id}.json, review items)
  ```
  It adds **purpose.md** beside schema.md. Schema holds structural rules; purpose holds goals, key questions and scope. Both are read on every ingest and query.
- **Page types**: source summary, entity, concept, query (saved answers in `wiki/queries/`), overview. Every page has YAML frontmatter with `type`, `title`, `sources: []`. The graph also uses type affinity.
- **Links**: `[[wikilinks]]`. **Cascade delete**: deleting a source removes its summary page. Shared entities only lose that source from `sources[]`. Removed pages are purged from index.md, and **dead `[[wikilinks]]` to deleted pages are stripped** from the remaining pages.
- **Immutability / ingested marker**: an SHA256 incremental cache skips unchanged sources. The `sources[]` frontmatter gives traceability, and a source summary page is always created, with a fallback if the LLM omits it.
- **index/log**: the LLM updates index.md, log.md and overview.md in the generation step. overview.md is regenerated on every ingest. A "deterministic `wiki/index.md` rebuilding" maintenance action was added later.
- **Ingest**: two-step chain of thought (an analysis call, then a generation call that writes files). A persistent serial queue retries up to 3 times. A folder watcher on `raw/sources/` reacts to add, edit and delete. There is also a Chrome clipper.
- **Lint / health**: a Lint panel, plus graph insights. These cover isolated pages (degree ≤1), sparse communities (cohesion <0.15) and bridge nodes. An **async Review queue** lets the LLM flag items for human judgement, with constrained actions (Create Page / Deep Research / Skip).
- **UI**: a 3-column desktop app with a Milkdown editor, a sigma.js graph and an Obsidian-compatible wiki dir. There is no git integration and no history view.
- **Issues seen**: "Page-Merge preserves path-prefixed [[wikilinks]]" (#576), stray code fences wrapping saved content (#575), agent stream timeouts, and folder import doing nothing on .deb.

### 2. AgriciDaniel/claude-obsidian (15.0k stars)
https://github.com/AgriciDaniel/claude-obsidian

- **Layout (user vault)**: `inbox/` (visible staging), `.raw/` (immutable, content-addressed captures, create-only), `wiki/`, `.obsidian/`, `.vault-meta/` (ignored runtime state), `.claude-obsidian.json`.
- **Ledgers instead of frontmatter-only provenance**:
  - `.raw/.manifest.json`: ingestion hashes, generated pages, address map
  - `wiki/meta/ledgers/source-ledger.json`: SHA-256 identity, authority (`official|primary|secondary|community|synthetic|unknown`), review state (`unreviewed|active|superseded|rejected`), `refresh_due`, `independence_key`
  - `wiki/meta/ledgers/claim-ledger.json`: claim assessment `accepted|provisional|contested|unsupported|deprecated`. A high-risk accepted claim needs two independent sources.
- **Page types**: these depend on `wiki-mode`. Generic mode uses sources, concepts, entities and sessions. LYT, PARA and Zettelkasten are alternatives. Switching modes routes only *new* notes and never bulk-moves old ones. Also present: `wiki/hot.md` (a hot cache), index.md, overview.md and MOCs.
- **Write model**: every operation is a **transaction bundle**. The tool records the expected SHA-256 of every target, workers return drafts only, and one orchestrator applies the change atomically. A planner emits `approved_plan_sha256`, which the user passes to `--apply`. It holds a vault lock, journals backups and supports `transaction recover`. "A changed target is a conflict, never a silent overwrite." A git checkpoint is a separate, explicit command.
- **Lint**: a deterministic, read-only engine with **no LLM involved**. It parses wikilinks, embeds, md links, aliases, heading and block fragments, and code fences. It skips dot-dirs, honours .gitignore, and `--exclude` covers scratch folders. Categories are dead or **ambiguous** links, orphans, missing required frontmatter (`title`), empty sections, stale index entries and ledger violations. It **never auto-fixes**: repair is a separate, user-selected transaction, and lint is re-run afterwards.
- **Ingest**: manual `/wiki-ingest` over a bounded batch with an explicit budget. A **compilation-value gate** means a thin source may get only a ledger record and no page. Source text is treated as untrusted (prompt-injection guidance).
- **Issues seen**: wiki-ingest `maxTurns: 30` is too low for mature vaults and ends silently mid-run. The BM25 tokenizer collapses CJK text. Running as a plugin, the scripts operate on the plugin cache dir instead of the vault. An auto-commit PostToolUse hook silently defers commits when the lock fails. There are hook event-type breakages across Claude Code versions.

### 3. Ar9av/obsidian-wiki (3.5k stars)
https://github.com/Ar9av/obsidian-wiki · docs/architecture.md

- **Layout**: `index.md`, `log.md`, `hot.md` (a ~500-word generated snapshot), `.manifest.json` (+ `.manifest.lock`), `_meta/taxonomy.md` (a controlled tag vocabulary), `_insights.md`, `_raw/` (staging for rough notes), `_staging/` (review queue when `WIKI_STAGED_WRITES=true`), `_archives/` (timestamped snapshots for rebuild), `concepts/ entities/ skills/ references/ synthesis/ journal/ projects/<name>.md`.
- **Frontmatter**: required `title, category, tags, sources, created, updated` plus a `summary` of 1–2 sentences. Queries read the summaries before page bodies, which keeps cost roughly flat from 20 to 2000 pages. A `provenance:` block summarises the share of extracted, `^[inferred]` and `^[ambiguous]` claims.
- **Source keys** are portable: vault-relative, `~`-relative, or `repo:`/`url:`/`agent:` pseudo-keys, never absolute paths.
- **Ingested marker**: `.manifest.json` maps each source path to timestamps and the pages it produced, and the next run processes only the delta. Code ingest records `last_commit_synced`.
- **index/log/hot**: written **only through a locked CLI** (`obsidian-wiki memory sync`), which takes the lock and replaces files atomically. This stops parallel agents from dropping each other's updates. hot.md is generated, except for one model-written "Key Takeaways" slot.
- **Lint and maintenance**: `wiki-lint` (orphans, broken wikilinks, stale content, contradictions, missing frontmatter), `wiki-dedup` (alias identity, "RSC" vs "React Server Components"), `cross-linker`, `tag-taxonomy`. **"Vault equilibrium"**: these skills optimise different objectives and can undo each other. A report-only mode checks that all of them propose nothing and detects *oscillation*.
- **Benchmark finding (PR #175)**: a plain agent routed graph questions through `index.md`, which links to every page. It "found" meaningless short paths and ranked `index` as the most important page. The fix is to **exclude bookkeeping files from the graph**.
- **UI**: Obsidian graph view, plus exports (graph.json, GraphML, Cypher, `graph.html`, OKF bundle). OKF v0.2 round-tripping is lossless.

### 4. atomicstrata/llm-wiki-compiler (`llmwiki`, 2.2k stars)
https://github.com/atomicstrata/llm-wiki-compiler · docs/concepts/wiki-model.mdx

- **Layout**: `sources/` (raw; top-level md by default, nesting opt-in), `wiki/concepts/`, `wiki/queries/`, `wiki/<entity>/` (typed by profile), `wiki/index.md` (**auto-generated TOC rebuilt after every compile**), root `log.md`, `.llmwiki/` (`state.json` holds per-source SHA-256 and **concept ownership**; also `schema.json`, `config.json`, `candidates/` review queue, `embeddings`, `eval/history.jsonl`).
- **Page kinds**: `concept`, `entity`, `comparison`, `overview`, plus saved queries. A `.llmwiki/profile.json` ("Configurable Lifecycle Profiles") can declare typed entities, relations, lifecycle state machines and review gates, and **these are enforced by the write path, not by prompts**.
- **Frontmatter**: `title, summary, kind, sources[], createdAt, updatedAt, aliases[]`, plus confidence, contradiction and review metadata. Body citations look like `^[source.md]`, with paragraph or line-range citations.
- **Links**: the compiler auto-links title mentions as `[[slug|Title]]`. The piped alias keeps resolution stable when filename ≠ title. `aliases:` frontmatter makes `[[MHA]]` resolve. It never auto-links inside code, link text, alt text or table cells.
- **Freshness**: each page is fresh, stale, orphaned (all sources deleted) or unverified. `llmwiki rm <source>` deletes pages derived *exclusively* from that source. `refresh --stale` recompiles the owners of stale pages.
- **log.md**: appended by the tool with a fixed parseable header, `## [ISO] op | desc`, followed by bullets of `[[links]]`.
- **Lint/eval**: `llmwiki lint` covers broken links, citations, metadata and freshness. `llmwiki eval` gives a health score, citation coverage and precision, wikilink-graph health, and an optional LLM judge. `llmwiki next` suggests the safest next action.
- **UI**: `llmwiki view` is a read-only local viewer with search, graph, freshness badges and citation chips. There is also an MCP server (`serve`) and a TS SDK. Version 1.4 adds review-before-publish for answers and batch page approval.

### 5. lucasastorian/llmwiki (1.6k stars)
https://github.com/lucasastorian/llmwiki

- **Layout**: points at an **existing user folder and never moves or modifies it**. It adds only `wiki/` (e.g. `overview.md`, `concepts/attention.md`) and a hidden `.llmwiki/` (SQLite `index.db`, extraction cache) that is rebuildable with `reindex`. "The filesystem is the source of truth; the index just makes it fast."
- **MCP tools**: `guide` (called first), `search` (including the citation graph: what cites what, stale or uncited pages), `read` (globs, page ranges), `create`, `edit` (exact find-and-replace), `append`, `delete` (overview.md and log.md protected), and `lint` (deterministic: citation resolution, dangling links, orphan/stale pages, frontmatter consistency). Pages use **footnote citations** back to sources.
- **Ingest trigger**: a watcher indexes new files immediately. *Synthesis* runs as a **scheduled nightly Claude Routine** ("find everything added since your last run…"). The Chrome extension stores highlights and comments as additional source material.
- **UI**: a Next.js wiki viewer with sources view and graph. Hosted mode uses Postgres + S3 behind the same `VaultFS` seam.

### 6. Astro-Han/karpathy-llm-wiki (1.6k stars)
https://github.com/Astro-Han/karpathy-llm-wiki · SKILL.md

- **Layout**: `raw/<topic>/YYYY-MM-DD-slug.md` (with a metadata header for URL, collected and published dates) and `wiki/<topic>/<article>.md`, **one level of topic dirs only**, plus `wiki/index.md` and `wiki/log.md`.
- **Links**: **standard relative markdown links**, not wikilinks. Each article has a `Sources:` field (author/org + date) and a `Raw:` field (relative links to raw files).
- **Grounding invariant**: every number, date and quote in wiki/ must exist verbatim in the linked raw files. `scripts/check_evidence.py` greps those literals during lint.
- **Ingest triage**: New / Update / Disputed / **No material**. A no-material source is kept in raw and logged with a machine-readable heading, so lint does not report it as an unreferenced raw backlog. Cascade updates use full-text search, not just the index. Superseded claims get a `Status: Outdated|Disputed` block and are never silently rewritten. Compilation is serial because index, log and cascade are shared state.
- **Lint tiers**:
  - Safe auto-fixes: index consistency (`[MISSING]` markers, not deletion), broken internal links with exactly one same-name match, and removal of dead See-Also links
  - Mechanical reports: evidence script, unreferenced raw files
  - Judgement reports: contradictions, orphans, missing pages for frequently mentioned concepts, archive pages whose sources changed
- **"Design Boundaries" (deliberately not built after 3 months of production logs)**: source-hash freshness (raw is immutable), line-number citations, numeric confidence scores, per-article review dates, access decay, retract machinery, hooks or schedules, vector or graph search ("at 50K–100K tokens grep and read are more reliable"), typed relation ontologies, MCP or UI. This is a useful counterweight to the heavier projects.

### 7. kfchou/wiki-skills (185 stars): a flat page folder, a generated index and git trailers as the log
https://github.com/kfchou/wiki-skills

- **Layout**: `SCHEMA.md` (conventions plus the wiki root path), `bin/`, `raw/`, `wiki/index.md` (**generated, gitignored**), `wiki/overview.md`, `wiki/pages/` (**flat, slug-named**), `assets/`.
- **index generated** from each page's `category` + `summary` frontmatter by `bin/generate-index.py`. Skills regenerate it before reading and after writing, which gives "no drift, no merge conflicts".
- **Log = git**: each operation is one commit carrying a `Wiki-Op:` trailer. `render-log.py` renders the history on demand. Skills **suggest a commit and commit only on confirmation**. Non-git wikis fall back to log.md.
- **Pre-commit gate** (deterministic, no LLM): it blocks a commit if a staged page has an unresolved contradiction flag, missing frontmatter, a broken `[[link]]` or a **slug collision**.
- **Slug = identity**: `wiki-merge` folds a duplicate into a survivor and **rewrites every inbound link**. Split separates an overloaded slug (`mercury-planet`/`mercury-element`) and repoints each link *by meaning*. Both end with a link-resolution sweep.
- **Other skills**: `wiki-audit` checks each footnote against its source with one subagent per source, and strong mode adds a cross-provider review. `wiki-update` always shows diffs before writing. `wiki-lint` writes a severity report to `wiki/pages/lint-<date>.md`.

### 8. ussumant/llm-wiki-compiler (325 stars)
https://github.com/ussumant/llm-wiki-compiler
- **Topic-based articles**: `wiki/INDEX.md`, `topics/`, `concepts/`, `schema.md`.
- **Coverage**: section headings carry `[coverage: high -- 8 sources]`.
- **Codebase mode**: it compiles READMEs, ADRs, OpenAPI files and docker configs into articles.
- **Two layers**: a global wiki (`~/Knowledge`) and a per-repo local wiki (`.wiki-compiler.json`).
- **Session start**: a SessionStart hook injects INDEX plus the relevant articles.
- **Token savings**: it claims about 84–90% savings compared with re-reading raw files.

### 9. tobi/qmd (30.3k stars)
https://github.com/tobi/qmd
- This is the search layer, not a wiki. It runs locally: BM25 + vector + HyDE query expansion, fused with RRF and an LLM reranker (GGUF via node-llama-cpp). It has an MCP server (`query`, `get`, `multi_get`, `status`, `metadata`) and a Claude Code plugin.
- Notable concept: **collections, each with a "context" string attached to a path tree** (`qmd context add qmd://notes "Personal notes"`). The context is returned with matching documents so the agent knows what kind of corpus a hit came from.
- obsidian-wiki uses qmd as an optional semantic search backend.

### 10. Hermes Agent bundled `llm-wiki` skill (NousResearch)
https://hermes-agent.nousresearch.com/docs/user-guide/skills/bundled/research/research-llm-wiki
- **Layout**: `SCHEMA.md`, `index.md`, `log.md`, `raw/{articles,papers,transcripts,assets}`, `entities/ concepts/ comparisons/ queries/`, `_archive/`, `_meta/topic-map.md`.
- **Frontmatter**: `title, created, updated, type, tags, sources`, with optional `confidence`, `contested` and `contradictions`. Raw files get `source_url, ingested, sha256` (the hash covers the body only, so a drift check is possible).
- **Index/log**: index is split past 50 entries, with a topic map past 200. log.md uses `## [YYYY-MM-DD] action | subject` and rotates to `log-YYYY.md` after 500 entries.
- **Lint list**: orphans, broken wikilinks, index completeness, required frontmatter and taxonomy tags, stale pages (90 days behind newer sources), contradictions, low-confidence and single-source pages, sha256 drift, pages over 200 lines, log rotation.
- **Rule**: confirm with the user before an ingest touches 10 or more existing pages.

### 11. Google Open Knowledge Format v0.2
https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
- **Bundle**: a directory of md + YAML files. **Concept ID = file path minus .md**. `index.md` and `log.md` are reserved at *any* directory level, and index MAY be generated. Git is the recommended distribution.
- **Fields**: required `type`. Recommended `title`, `description`, `tags`, `resource`. Provenance is `sources[]` (`id`, `resource`, `title`, `author`, credibility signals). Trust uses `generated: {by, at}` and `verified: [{by, at}]` with actors `agent/version`, `human:<id>` and `process:<id>`, giving tiers unverified, machine-confirmed and human-reviewed. Lifecycle is `status: draft|stable|deprecated` plus `stale_after`.
- **Links**: **standard markdown links. A bundle-absolute `/dir/x.md` is recommended** because it survives moves within a subdirectory. Link semantics live in the prose. **Consumers MUST tolerate broken links**, which may be not-yet-written knowledge.
- **Adoption**: llmwiki and obsidian-wiki both import and export OKF. Astro-Han tracks it but considers it immature.

---

### Field reports and failure modes (blogs)

- **Felipe Fontoura, "How to Keep It From Becoming Legacy"** (https://felipefontoura.com/articles/llm-wiki/):
  - Failures he saw: summaries of summaries (an AI meeting summary ingested as if it were a transcript), misattribution (15 quotes not found in the cited transcript), premature concept pages built on one source, "38% of pages semantic near-duplicates" after a batch backfill, smoothed contradictions, invented references, silent link decay (42 and 186 dangling links in two vaults), and **flat index.md breaking down past roughly 100–200 pages**.
  - His fixes: organise folders by *maturity* (inbox → sources → forming → wiki) rather than topic; require two sources before a new concept page; run a script for dangling links and orphans; **exclude index.md when computing orphans**; keep model passes for judgement work; **check quotes by script**; end each operation with one commit; undo with `git revert`; review diffs in git instead of approving each change.
- **"Karpathy's LLM Wiki, Six Months In"** (https://www.openaitoolshub.org/en/blog/karpathy-llm-wiki):
  - The agent "smoothed" the author's own originals, so originals became verbatim-only (`do-not-rewrite`).
  - An older page was overwritten by a contradicting newer one. The fix was a `contradicts:` field.
  - Stale pricing claims led to adopting the "LLM Wiki v2" lifecycle fields `last_verified`, `confidence`, `superseded_by`.
  - A tool migration dropped `aliases`, so one person ended up on two pages.
  - The author also added a weekly link-check job.
- **"I built Karpathy's LLM Wiki twice"** (https://pub.towardsai.net/i-built-karpathys-llm-wiki-twice-once-as-code-once-as-a-md-heres-what-each-one-gives-up-08b31170999a):
  - The skill-only version loses deterministic IDs (slugified titles) and structural guarantees.
  - Failures seen: malformed markdown, YAML broken by unquoted colons, duplicate H1s, and section order drifting on regeneration.
  - The conclusion is that code should own structure, identity, validation and lint, and the LLM should own drafting and repair *decisions*.

---

### Cross-cutting patterns
1. **Raw is immutable, everywhere.** Every implementation keeps the original read-only. The more careful ones add a visible **staging inbox** in front of it (claude-obsidian `inbox/`, obsidian-wiki `_raw/`, Fontoura's maturity folders) and store raw captures content-addressed or hashed.
2. **The "ingested" marker lives outside the page tree**: a manifest or state file keyed by source hash, mapping source → produced pages (llmwiki `state.json` ownership, obsidian-wiki `.manifest.json`, claude-obsidian `.raw/.manifest.json`, nashsu SHA cache). Pages carry `sources:` back-references in frontmatter, so the mapping is bidirectional. Astro-Han's lightweight alternative logs a "no material" disposition so a raw file without pages is not flagged.
3. **Typed pages are the norm.** The common set is entity, concept, source-summary, comparison/synthesis, query (saved answer) and overview. Most projects use subfolders per type. Exceptions are kfchou (flat `pages/` + `category` frontmatter) and Astro-Han (topic folders).
4. **The near-universal frontmatter** is `title, type|kind|category, summary|description, sources[], created, updated, tags`, often with `aliases`. Confidence, contested and status fields are increasingly common.
5. **Links**: `[[wikilinks]]` dominate because of Obsidian. The robust implementations resolve by **slug plus aliases**, writing `[[slug|Title]]`, not by raw title. Astro-Han and OKF use plain markdown links (OKF recommends bundle-absolute paths). Dead-link handling ranges from auto-strip (nashsu, on delete) and inbound-link rewriting on merge or rename (kfchou) to report-only (claude-obsidian) and "tolerate" (OKF).
6. **Index is moving from LLM-maintained to generated.** llmwiki, kfchou and obsidian-wiki (via a locked CLI) generate it; nashsu added a deterministic rebuild. The LLM-maintained index is the most common source of drift.
7. **The log is often a tool-appended, parseable `log.md`.** kfchou uses git commits with trailers, and Fontoura recommends one commit per operation.
8. **Lint is split into a deterministic pass and an LLM judgement pass.** The deterministic pass covers dead and ambiguous links, orphans (excluding index), frontmatter, slug collisions, index staleness and quote grep. The LLM pass covers contradictions, stale claims, missing pages and dedup. The careful implementations **never auto-fix silently**.
9. **Concurrency.** Index, log and manifest are shared state, so implementations either serialise ingest or use locks and atomic replace (obsidian-wiki, claude-obsidian).
10. **Human review queue.** A staging or candidates directory holds LLM writes before they publish (llmwiki `candidates/`, obsidian-wiki `_staging/`, nashsu Review).

---

## Part 2. Coding agents, memory frameworks and knowledge apps
### 0. Reference pattern: Karpathy "LLM Wiki" [P]

Source: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

- Three layers: **raw sources** (immutable; "the LLM reads from them but never modifies them"), **the wiki** (LLM-written Markdown: summaries, entity/concept pages, comparisons), **the schema** (CLAUDE.md / AGENTS.md describing conventions and workflows).
- Operations: **ingest** (one source may touch "10-15 wiki pages"; update index, log), **query** (answers cite pages; good answers filed back as pages), **lint** (contradictions, stale claims, orphans, missing links).
- `index.md` = catalogue with link + one-line summary per page, read first; claimed to work "at moderate scale (~100 sources, ~hundreds of pages)" without embeddings. `log.md` = append-only, greppable.
- Knowledge "compiled once and then kept current, not re-derived on every query". Optional local search (e.g. qmd) once the index stops being enough. No benchmarks; intentionally abstract.

---

### 1. Coding-agent knowledge / memory

#### Claude Code [P]
Source: https://code.claude.com/docs/en/memory ; https://code.claude.com/docs/en/skills ; https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **Storage:** plain Markdown files. `CLAUDE.md` / `CLAUDE.local.md` / `AGENTS.md` (read natively since v2.1.277), hierarchical (org/user/project/subdir); `@path` imports (max 4 hops); `.claude/rules/*.md` with optional `paths:` frontmatter (path-scoped, load only when matching files are touched); skills (`SKILL.md` + supporting files).
- **Auto memory:** `~/.claude/projects/<project>/memory/` = `MEMORY.md` **index, one line per memory**, plus one topic file per memory with `type` frontmatter (`user`, `feedback`, `project`, `reference`). First 200 lines / 25KB of `MEMORY.md` loaded every session; topic files read on demand with normal file tools. Harness warns when the index nears the limit and tells Claude to "keep one line per entry, move detail into topic files, and merge or drop stale entries". Claude skips anything derivable from code/git. Machine-local, not versioned (no git).
- **Skills = progressive disclosure:** only name+description (capped 1,536 chars) always in context; body loads on invocation; sibling reference files read on demand. "Keep SKILL.md under 500 lines."
- **Retrieval:** always-loaded instructions + catalogue/index; everything else via agentic search (glob/grep/read). Anthropic: "CLAUDE.md files are naively dropped into context up front... primitives like glob and grep allow it to navigate its environment and retrieve files just-in-time" (hybrid strategy).
- **RAG dropped:** Boris Cherny (Claude Code lead) on X: "Early versions of Claude Code used RAG + a local vector db... we found pretty quickly that agentic search generally works better" (also simpler; avoids security/privacy/staleness/reliability issues). https://x.com/bcherny/status/2017824286489383315 (quoted via https://smartscope.blog/en/ai-development/practices/rag-debate-agentic-search-code-exploration/ — X blocks fetch).
- **Curation:** human writes CLAUDE.md/rules/skills (checked into git); Claude writes auto memory.

#### OpenAI Codex [P]
Source: https://learn.chatgpt.com/docs/agent-configuration/agents-md ; https://learn.chatgpt.com/docs/customization/memories
- **AGENTS.md:** global `~/.codex/AGENTS.md` (or `AGENTS.override.md`), then project root → cwd, at most one file per directory, concatenated root-down (deeper wins). Stops at `project_doc_max_bytes` (default **32 KiB**).
- **Memories (off by default):** background pipeline turns "useful context from eligible prior chats" into local files under `~/.codex/memories/` (summaries, durable entries, recent inputs, supporting evidence). Two-stage: per-chat **extraction** model + global **consolidation** model; skips active/short sessions; redacts secrets. Files are "generated state" — don't hand-edit as primary control surface. Docs: keep required team guidance in AGENTS.md / checked-in docs; memories are "a recall aid".
- Skills also supported (SKILL.md, same progressive-disclosure model) [S].
- **Retrieval:** always-loaded AGENTS.md chain + injected memories + agentic shell search (rg). No vector index.

#### Cursor [P]
Source: https://cursor.com/docs/context/rules ; https://cursor.com/blog/semsearch ; https://forum.cursor.com/t/are-my-memories-gone/144057
- **Rules:** `.cursor/rules/*.mdc` with frontmatter (`description`, `globs`, `alwaysApply`) → modes Always / Auto-attached by glob / Agent-requested by description / Manual (@). User rules, Team rules (dashboard, enforceable), AGENTS.md (nested). `@file` refs in rules are pointers, read on demand, not inlined.
- **Memories removed:** staff: "The Memories feature was intentionally removed starting from version 2.1.x"; users told to "Export memories" to an .mdc and put it in Rules. I.e. auto-generated memory folded back into human-owned rule files.
- **Retrieval:** hybrid — grep + **semantic search with a custom embedding model trained on agent sessions**. Offline: +12.5% average answer accuracy (6.5–23.5% by model); online A/B: +0.3% code retention overall, +2.6% on 1,000+ file codebases; 2.2% more dissatisfied follow-ups without it. "The combination of these two leads to the best outcomes." Docs indexing (@Docs) is also embedding-based [S].
- Strongest public counter-evidence to "grep only" — but measured on large codebases, not small curated knowledge bases.

#### Windsurf / Cascade (now under Devin Desktop docs) [P]
Source: https://docs.devin.ai/desktop/cascade/memories
- **Memories:** auto-generated by Cascade, stored locally per workspace in `~/.codeium/windsurf/memories/`, not committed; only for the legacy Cascade agent (not the new default Devin Local agent).
- **Rules:** global `global_rules.md` (6,000 chars, always on); workspace `.devin/rules/*.md` (fallback `.windsurf/rules/`), 12,000 chars each, `trigger:` = `always_on` / `model_decision` (description only in prompt, body loaded when relevant) / `glob` / `manual`. AGENTS.md through the same engine. Docs: rules are "better for durable, shareable knowledge".
- Codebase retrieval historically uses an embedding index + agentic tools (Fast Context) [S].

#### Devin Knowledge + DeepWiki [P]
Source: https://docs.devin.ai/product-guides/knowledge ; https://docs.devin.ai/work-with-devin/deepwiki
- **Knowledge:** short items ("a handful of sentences") each with a **trigger description**; recalled "when relevant, not all at once"; repo-pinned items always used in that repo. Devin *suggests* items from chat feedback; human edits/approves/dismisses. **Now being deprecated in favour of Skills** (auto-migrated).
- **DeepWiki:** a **compiled wiki of a repo**: pages with title/purpose, nested via `parent`, architecture diagrams, links to source. Steerable via `.devin/wiki.json` (`repo_notes`, `pages`; ≤30 pages, 80 enterprise). Regenerated (no described incremental update; "commit the file and regenerate"). "Ask Devin" combines wiki + code search. Closest commercial analogue to the LLM-Wiki "compiled pages" idea, but generated in batch, not incrementally maintained.

#### GitHub Copilot [P]
Source: https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/ ; https://docs.github.com/en/copilot/concepts/agents/copilot-memory ; https://docs.github.com/en/copilot/concepts/context/spaces
- **Custom instructions:** `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md` (applyTo globs), AGENTS.md [S].
- **Copilot Memory:** each memory = subject + fact + **citations to code locations** + reason; agents create via a tool call. **Just-in-time verification** instead of an offline curation service: before use, the agent checks citations against the current branch; contradicted → store corrected version; verified → re-store (refresh timestamp). Unused entries deleted after **28 days**. Repo-scoped (write-permission to create). Results: code review precision +3%, recall +4%; coding-agent PR merge rate 83%→90%; p<0.00001.
- **Spaces:** curated bundles of repos, files, PRs, issues, free text, uploads; GitHub sources auto-sync. Retrieval method not documented (repo indexing is semantic per separate docs [S]).

#### Cline Memory Bank [P]
Source: https://docs.cline.bot/prompting/cline-memory-bank
- A *prompting convention*, not a feature: `memory-bank/` with fixed files `projectbrief.md` → `productContext.md`, `systemPatterns.md`, `techContext.md` → `activeContext.md`, `progress.md`. "I MUST read ALL memory bank files at the start of EVERY task." Updated by the agent on new patterns, after significant changes, or on "update memory bank". Git-versioned with the repo. Full-load retrieval — doesn't scale past a handful of files.

#### Roo Code [P]
Source: https://roocodeinc.github.io/Roo-Code/features/codebase-indexing/
- Rules in `.roo/rules/` (+ mode-specific) [S]. Optional **codebase indexing**: tree-sitter AST chunks (100–1,000 chars; Markdown split by headers), embeddings (OpenAI/Gemini/Ollama/…), Qdrant; exposes `codebase_search` tool alongside normal file/grep tools.

#### Aider [P]
Source: https://aider.chat/docs/repomap.html
- `CONVENTIONS.md` loaded as read-only file [S]. **Repo map**: symbol definitions per file, graph-ranked (files as nodes, dependency edges), ~1k-token budget sent with each request. No embeddings/RAG. A generated *catalogue*, recomputed each time.

#### Continue [P]
Source: https://docs.continue.dev/reference/deprecated-codebase
- `@Codebase` embeddings context provider (and `@Docs`) **deprecated** "in favor of a more integrated approach" — agent mode with tools; rules in `.continue/rules` [S].

#### Kiro [P]
Source: https://kiro.dev/docs/steering/
- `.kiro/steering/*.md` (+ global `~/.kiro/steering/`). Generated foundation files `product.md`, `tech.md`, `structure.md` (always included). Inclusion modes `always` / `fileMatch` / `manual` / `auto` (name+description). Live file refs `#[[file:path:start-end]]`. AGENTS.md always included.

#### Augment [P, vendor claims]
Source: https://www.augmentcode.com/context-engine
- Proprietary **Context Engine**: real-time semantic index across repos ("not just grep or keyword matching"), offered also as an MCP server. Claims vs Claude Code on Opus 4.7: Terminal-Bench 2.0 same solve rate at 33% lower cost; SWE-Bench Pro 1.65B vs 2.35B tokens, +1.9 pts. Vendor-run, no grep-only baseline. Augment "Memories" = agent-written Markdown file [S].

**Coding-agent pattern summary:** converged on (1) human-owned Markdown instruction files in git, always loaded, with a cross-tool standard (AGENTS.md); (2) **progressive disclosure** — description/catalogue in context, body on demand (skills, model_decision rules, agent-requested rules, Kiro `auto`, Devin triggers, Claude MEMORY.md index); (3) agentic search (grep/glob/read) as the base retrieval, with semantic indexes as an *optional* add-on for large codebases (Cursor, Augment, Roo); (4) agent-written memory either kept as small indexed files (Claude), background-consolidated (Codex), or abandoned/merged into rules (Cursor removed Memories; Devin Knowledge → Skills; Windsurf memories legacy-only).

---

### 2. Agent memory frameworks

#### Letta / MemGPT [P]
Sources: https://docs.letta.com/guides/agents/memory-blocks ; https://www.letta.com/blog/context-repositories ; https://www.letta.com/blog/benchmarking-ai-agent-memory
- **Memory blocks:** labelled, size-limited (chars) text sections always in context, edited by the agent via memory tools; shareable across agents; optional read-only. Plus archival (vector) memory and recall (conversation search) [S].
- **Context Repositories (Feb 12, 2026, Letta Code `/memfs`):** memory becomes a **git-backed local file tree**; each file has frontmatter description; **file tree always in system prompt**; `system/` folder = fully loaded; other files read on demand. Every change committed with a message; subagents write in isolated git worktrees and merge via git conflict resolution; **sleep-time reflection** subagent writes memories in a worktree and merges back; **defrag** skill splits/merges into "a clean hierarchy of 15–25 focused files". This is essentially a compiled, versioned Markdown wiki for agent memory.
- **Benchmark:** Letta filesystem agent (gpt-4o-mini, tools grep/search_files/open/close) scored **74.0% on LoCoMo** vs Mem0's best graph variant 68.5%. Conclusions: agents are good at filesystem ops; "agent capability matters more than the retrieval mechanism"; simpler tools may beat knowledge graphs which "can be harder for the LLM to understand".

#### Zep / Graphiti [P]
Source: https://help.getzep.com/graphiti/getting-started/overview
- **Temporal knowledge graph:** ingest **episodes** (raw messages/docs kept as provenance nodes [S]); LLM extracts entities + fact edges; bi-temporal tracking; contradictions handled by **temporal edge invalidation** (old facts kept, marked invalid). Incremental updates. Retrieval: hybrid vector + BM25 + graph traversal, reranked (e.g. node distance), no LLM in retrieval loop. Needs a graph DB (Neo4j/FalkorDB/Kuzu).

#### mem0 [P]
Sources: https://docs.mem0.ai/core-concepts/memory-operations/add ; https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm
- Units: short extracted facts (LLM extraction, or `infer=False` stores raw). Vector store (+ optional graph memory [S]).
- **April 2026 algorithm change: ADD-only.** Dropped the ADD/UPDATE/DELETE reconciliation pass because "that reconciliation step was slow, and it was where context got destroyed"; new facts sit beside old ones, preserving history. Retrieval = semantic + keyword + entity-match fused. Claims LoCoMo 71.4→92.5, LongMemEval 67.8→94.4, <7k tokens/query (single-pass retrieval, managed platform).
- Lesson: LLM in-place rewriting of memory loses information; append + rank is safer.

#### Cognee [P]
Source: https://docs.cognee.ai/core-concepts/overview
- v1.0 ops remember / recall / improve / forget (legacy add / cognify / memify / search). DataPoints → graph nodes; three stores: relational (documents, chunks, provenance), vector, graph. Optional RDF/OWL ontologies. Graph-backed, session-aware recall.

#### LangMem [P]
Source: https://langchain-ai.github.io/langmem/concepts/conceptual_guide/
- Semantic memory as **collections** (many records, reconciled) or **profiles** (one document updated in place); episodic (few-shot examples); procedural (prompt optimisation). Formation in **hot path** (latency) or **background** reflection. Stored in LangGraph BaseStore with namespaces; key lookup, metadata filter, semantic search.

#### Basic Memory [P]
Sources: https://docs.basicmemory.com/ ; https://docs.basicmemory.com/concepts/knowledge-format
- "A knowledge graph written in plain Markdown". Notes have YAML frontmatter (title, type, tags, **permalink** — stable, path-derived, survives renames); **observations** `- [category] content #tags (context)` indexed individually; **relations** `- relation_type [[Target]]` (typed wikilinks). Local index (SQLite [S]) with full-text + semantic search (v0.23 "search release", reranking; Postgres FTS); MCP tools (write_note, read_note, search, build_context with `memory://` URLs [S]). Obsidian-compatible; written by AI via MCP and by the human. The closest open-source analogue to a plain-Markdown wiki with typed links.

---

### 3. Knowledge apps with AI

| Product | Notes |
|---|---|
| **Obsidian + Copilot plugin** [P] https://docs.obsidiancopilot.com/vault-search-and-indexing | Copilot V4 **dropped its in-plugin embedding index**: Agent Chat "uses ordinary file tools for exact text and file lookup"; Obsidian CLI skill for links/backlinks/properties/tags/Bases; semantic search only via external service (Miyo) as an *agent skill*. Plain Markdown vault, wikilinks, git optional. |
| **Smart Connections** [P] https://github.com/brianpetro/obsidian-smart-connections | Local embedding model; note-level (blocks in Pro); index in `.smart-env/`; "Connections" view of semantically related notes; drag a result to create a link — embeddings used for *link suggestion*, not as the store. |
| **Notion AI** [P] https://www.notion.com/help/notion-ai-security-practices | Blocks/pages in Notion's DB; "an embedding for each Notion page... stored in a vector database (e.g., Turbopuffer)". Vector RAG + agent. Page history versioning. |
| **Mem** [S] | Mem 2.0 "self-organizing" notes; AI auto-organises into collections; semantic search/chat. Vendor-managed. |
| **Reflect** [P] https://reflect.app/blog/ai-search | Daily notes + backlinks; "client-side embedding to build up a semantic index" for similar notes; chat over search results. |
| **Logseq** [S] | Outliner, blocks as units; file graph (Markdown) and new DB version (SQLite); no first-party AI retrieval; community MCP / embedding plugins. |
| **Tana** [P] https://outliner.tana.inc/learn/features/tana-ai | Node graph with **supertags + fields** (typed schema); AI fills fields from voice/transcripts, event-triggered commands, @-mention nodes as chat context; MCP/API. Structure-first, not vector-first. |
| **Capacities** [S] | Object-based (typed objects, properties, backlinks); AI assistant over objects. |
| **NotebookLM** [P/S] https://support.google.com/notebooklm/answer/16215270 | Sources are copies (or synced Drive docs); source-grounded answers with passage citations; user notes can become sources; ~50 sources free / more paid. Raw sources kept; no compiled layer except generated briefings/mind maps. |
| **Open WebUI** [P] https://docs.openwebui.com/features/rag/ | Classic chunk+embed RAG; optional hybrid BM25 + CrossEncoder rerank; citations. |
| **AnythingLLM** [P] https://docs.anythingllm.com/llm-not-using-my-docs | Chunk vectors, "4-6 text chunks" per query; docs admit vector search "is not a purely semantic process" and "no guarantee that relevant text stays together"; added full-document attach (v1.8.5) and agents. |
| **Dify** [P] https://docs.dify.ai/en/guides/knowledge-base/create-knowledge-and-upload-documents/chunking-and-cleaning-text | Chunk modes general / parent-child; High-Quality (vector) vs Economical (keyword) index; hybrid + rerank [S]. |
| **RAGFlow** [S] | Deep document parsing + template chunking; hybrid vector/full-text; optional knowledge graph and RAPTOR summaries. |
| **Microsoft GraphRAG** [P] https://microsoft.github.io/graphrag/ | TextUnits → entities/relationships/claims → Leiden communities → bottom-up **community summaries** (a compiled layer). Query: Global (summaries), Local (entity neighbourhood), DRIFT, Basic (vector). Expensive indexing; prompt-tuning needed. |
| **LightRAG** [P] https://github.com/HKUDS/LightRAG | LLM-extracted entity/relation graph + vectors; modes local / global / hybrid / naive / mix (default); incremental insert/delete; KV + vector + graph + doc-status stores. |

---

### 4. Evidence on what works

1. **Claude Code: vector RAG → agentic search.** Cherny: "agentic search generally works better", plus simpler and no staleness/privacy issues. (X post above.)
2. **Cursor: hybrid wins on large codebases.** Semantic search +12.5% accuracy offline; +2.6% code retention on 1k+ file repos, +0.3% overall. https://cursor.com/blog/semsearch
3. **Letta: filesystem beats specialised memory.** 74.0% LoCoMo with grep/open vs Mem0 graph 68.5%. https://www.letta.com/blog/benchmarking-ai-agent-memory
4. **Copilot: citation-backed facts + just-in-time verification** beat offline curation; +7pt merge rate. https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot/
5. **mem0: in-place LLM rewrite destroys context** → ADD-only + hybrid ranking. https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm
6. **LLM-compiled wiki vs single-round vector RAG** (Cochran, arXiv 2605.18490, 24 papers / 13 Qs, preregistered): wiki much better at connecting findings and claim-level citation support; RAG supported on single-fact lookup; wiki ~2 orders of magnitude more expensive to build and ~21× more tokens/query → "no break-even point exists"; a decomposition-retrieval RAG removed most of the synthesis advantage but not the citation advantage; "no architecture here was best on all three". https://arxiv.org/abs/2605.18490
7. **Progressive disclosure for LLM-maintained wikis** (Cochran, arXiv 2607.04576, real 709-page LLM-maintained wiki): catalogue + one-line summary per page retrofit; quality non-inferior; cost down ~⅓ (self-routing agent) to >½ (catalogue preload). Notable pilot finding: a capable agent "never loads the index, inferring a page's path from the question and reading it directly" — predictable paths/naming matter as much as the index. https://arxiv.org/abs/2607.04576
8. **Anthropic context engineering:** hybrid of up-front files + just-in-time glob/grep; structured note-taking outside context window; memory tool is file-based. https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
9. **Product retreats from embedding-first:** Continue deprecated @Codebase; Obsidian Copilot dropped its in-plugin index for file tools; Cursor removed Memories in favour of rule files; Devin Knowledge → Skills.
10. **Long-context vs RAG literature:** no silver bullet (LaRA, ICML 2025: https://proceedings.mlr.press/v267/li25dv.html; https://arxiv.org/abs/2501.01880).

---


---

## Part 3. History, change logs and sources in the UI
### Per-document history

| Product | Entry point | What opens | Doc visible? | Diff | Restore | Collection/workspace feed |
|---|---|---|---|---|---|---|
| Notion [V] | `•••` page menu → "Version history"; also clock icon top-right ("View all updates") opens Updates sidebar | Large modal: version list on right, version preview on left | Replaced by preview inside modal | Highlights changed blocks (added/deleted text, some non-text) | "Restore" button, preview first; reversible | Inbox ("All workspace updates"), per-page Updates sidebar (edits + analytics) |
| Google Docs [V] | "Last edit" / clock icon top-right; File → Version history | Right-side version panel; doc area shows selected version read-only | The doc area shows the old version (not current) | "Show changes" colored by editor | "Restore this version" at top → confirm; named versions, "only show named" filter | None (Drive activity panel per folder [K]) |
| Confluence [V] | `•••` More options → Page History; Page Information → "View changes" | Full page: version table with checkboxes | No (navigates away) | Compare selected: green add / red delete / blue format; unchanged collapsed; << >> step | "Restore this version" + change comment; creates new version | Space "Recent changes"/activity [K] |
| GitBook [V] | History icon in section header or Action menu | Right side panel listing edits, merged change requests, Git Sync ops | Yes; content shows that point in time | "Show changes" toggle marks changed blocks with left-gutter icon | Hover → Actions → Rollback | Change requests list per space (PR-like); history panel is space/section-level, not page-level |
| Outline [V partly] | Click "last edited" timestamp, or menu → History [K] | Right history sidebar [V]; doc pane renders selected revision [K] | Yes (doc pane stays, shows revision) | Rich inline diff (also in email notifications) [V] | "Restore" on revision [K] | Collection pages show recent activity [K] |
| Slab [V] | `…` menu → "View history" | "Versions" sidebar | Yes, doc pane becomes diff | Red removed / green added, shift-click range, change counter + up/down stepping | "Restore this version" at top; old version kept | — |
| Coda [V] | `⋮` → "Doc history"; "Open page history" per page | Right panel with tabs "This doc" / "This page" | Yes, doc shows past state | Green add / red removed per edit batch | "Copy this version" (new doc); true restore via support | Doc-level tab is effectively a doc-wide change log |
| Dropbox Paper [V] | `…` → "Doc history" | Window with tabs "Doc changes" / "Comment history"; clicking opens version full-screen | No | None described | "Roll back to this version"; Undo | — |
| Craft [V] | Right sidebar Info tab → "View Backups" | Backup list, preview | Preview | None | Restore | — |
| Linear docs [V partly] | `…` → "Show document history" | History view (details not documented) | — | — | Restore exists (guideflow tutorial) | Project activity/updates feed [K] |
| Obsidian Sync [V] | File explorer context menu → "Open version history" | Modal: version list left, content right | Modal over doc | Not in Sync (File Recovery has "Show changes") | "Restore" replaces content | Settings → Sync → "Deleted files" vault-level list |
| Obsidian File Recovery [V] | Settings → File recovery → Snapshots "View" | Modal with file picker then snapshots | Modal | "Show changes" toggle | "Copy" or "Restore" | — |
| obsidian-git [V] | Commands "Open history view", "Open source control view", "Open diff view" | Side panes (history = commit list with changed files) | Yes | Diff view per file; line authoring gutter | via git | History view IS a repo-level commit log listing touched files |
| Logseq [K] | Page title context menu → "Check page history" (git-based, desktop) | Panel/modal of commits | — | git diff | Manual | — |
| Anytype [K] | Object `…` menu → "Version history" | Right sidebar version list; object shows selected version | Yes | Highlights changes | "Restore" | — |
| GitHub [V partly] | File header: Preview / Code / Blame segmented toggle [V]; "History" (clock) button → commits list [K] | History = full commits page filtered to path; Blame = inline mode on file | Blame yes, History no | Commit diff page | Revert via PR | Repo commits list + Activity view (one row per push/commit, files touched) [K] |
| DeepWiki [K] | No history UI; wiki shows "Relevant source files" chips at top of each page linking to code; header shows last indexed commit + refresh | — | — | — | — | — |
| Docusaurus / Mintlify [V Mintlify] | Changelog is a dedicated page; Mintlify `<Update label=date tags>` timeline entries, tag filters in right panel, RSS per entry | Full page | n/a | n/a | n/a | That page IS the collection-level log |

### Source vs generated views

- NotebookLM [V]: fixed three columns — Sources (left, inputs; Drive docs stay linked, PDFs fixed), Chat (middle), Studio (right, generated outputs/notes). A note can be "converted to source"; Deep Research reports can be added back as sources. Distinction is by panel placement, not badges. [K] Clicking a source swaps the Sources column into a source viewer with a "Source guide" summary; checkboxes select which sources are in scope.
- Claude Projects [K]: right-side "Project knowledge" panel listing uploaded files + instructions, separate from chats; capacity meter.
- Perplexity Spaces [K]: Space page with Files/Links section (sources) separate from threads (generated).
- Common pattern: inputs listed in a persistent secondary panel; generated content is the main surface; never mixed in one undifferentiated tree.

### Dominant patterns

1. History is a secondary action (overflow menu or clock/"last edited" affordance in the top-right), never a peer tab of the document.
2. Modern editors (Google Docs, GitBook, Outline, Slab, Coda, Anytype) open a right-side panel and keep the document pane, re-rendering it as the selected version with inline diff highlights. Older/enterprise tools (Confluence, Paper) navigate to a full page; Notion/Obsidian use a modal.
3. Diff = inline green/red on the rendered doc, with a "Show changes" toggle (GitBook, Obsidian, Google). Side-by-side is rare.
4. Restore = single primary button at top of the version view, non-destructive (creates new version), sometimes with a preview/confirm.
5. Collection-level feeds exist where content is commit-like: GitBook change requests, obsidian-git history view (commit → files), GitHub commits/activity, Coda "This doc" tab, Confluence space activity. Notion's feed is notification-centric (Inbox).
6. "Last edited by X, time" in the header doubling as the history entry point (Google Docs, Outline) is the most discoverable affordance.

### Sources
- https://www.notion.com/help/duplicate-delete-and-restore-content
- https://www.notion.com/help/updates-and-notifications
- https://www.notion.com/releases/2023-02-09
- https://support.google.com/docs/answer/190843
- https://confluence.atlassian.com/display/DOC/Page+History+and+Page+Comparison+Views
- https://gitbook.com/docs/create-content/version-control
- https://gitbook.com/docs/collaborate/change-requests
- https://www.getoutline.com/changelog/diff-view
- https://help.slab.com/en/articles/3779596-post-version-history
- https://help.superhuman.com/hc/en-us/articles/46210368657293-View-and-copy-doc-history (Coda)
- https://help.dropbox.com/files-folders/paper/track-restore-changes-comments
- https://support.craft.do/en/write-and-edit/version-history
- https://www.guideflow.com/tutorial/how-to-see-document-history-in-a-project-on-linear
- https://obsidian.md/help/sync/version-history
- https://obsidian.md/help/plugins/file-recovery
- https://github.com/vinzent03/obsidian-git
- https://discuss.logseq.com/t/log-error-fatal-not-a-git-repository-or-any-of-the-parent-directories-git/2577
- https://docs.github.com/en/repositories/working-with-files/using-files/viewing-and-understanding-files
- https://docs.devin.ai/work-with-devin/deepwiki
- https://www.mintlify.com/docs/components/update
- https://libguides.uprm.edu/notebooklm/interface_panels
- https://www.jeffsu.org/notebooklm-changed-completely-heres-what-matters-in-2026/

---

## Patterns and trade-offs

- **Compiled wiki versus retrieval is a cost trade, not a winner-take-all.** A compiled wiki answers cross-document questions and cites better; retrieval over raw chunks is cheaper to build and does better on single-fact lookup. Implementations that last keep both: pages for synthesis, grep over raw sources for exact facts.
- **What breaks first is identity.** Title-based links, LLM-written indexes and lost `aliases` produce dead links and duplicate pages; slugs plus aliases and generated indexes hold up.
- **Ingest state is either a manifest or derived from `sources:` back-references.** A manifest is one more shared file to lock; back-references put the mapping where a reader already looks.
- **Unattended maintenance passes interfere.** Separate passes that each "fix" the corpus undo one another; the careful tools report and let a person choose.
- **History UIs converge on a side panel.** The document stays in view, the selected version is highlighted inline, and restore adds a new version; tabs that replace the document are absent.

## Worth borrowing / worth avoiding

**Borrow:** immutable raw sources with the original kept; `sources:` back-references on pages; slug identity with `aliases`; a generated, size-capped catalogue; git commits with an operation trailer as the log; a deterministic lint layer before any LLM judgement; report-only LLM lint; a side-panel history with inline changes; sources shown apart from generated pages.

**Avoid:** LLM-maintained indexes; links by raw title; silent auto-fix passes; summaries of summaries ingested as primary sources; ingest runs that can be cut off by an agent's turn limit without saying so; unquoted YAML values that break frontmatter.
