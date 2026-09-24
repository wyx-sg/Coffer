# Knowledge curation: how other products do it

**Feature**: a knowledge base of plain Markdown files that people and an LLM co-maintain — new material lands in an inbox, an LLM pass merges it into the existing documents (newer wins, human edits respected), and agents read the files with their own tools, guided by a generated catalogue, instead of through RAG retrieval · **Coffer spec**: [knowledge](../../openspec/specs/knowledge/spec.md) · **Related ADRs**: [Knowledge Is Plain Files](../decisions/knowledge-is-plain-files.md), [Knowledge Curation](../decisions/knowledge-curation.md), [Coffer Ships Its Own Skill](../decisions/coffer-ships-its-own-skill.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (repos, official docs, author posts); star counts via the GitHub API, 2026-09-24

The field splits three ways:

1. **LLM-maintained Markdown wikis.** Karpathy's "LLM Wiki" and the projects built on it, DeepWiki, and Mem's AI edits. Here an LLM writes and rewrites pages, and readers navigate them through an index.
2. **Files plus a derived index.** Obsidian with its AI plugins, Basic Memory, and Khoj. People own the files, and a search index or embedding sidecar sits beside them.
3. **Opaque stores.** Cognee, AnythingLLM, Notion AI, Claude Projects past its limit, and Cursor @Docs. The corpus lives in a vector store or graph, and agents reach it only through a search API.

A fourth group decides how agents *discover* content: agent-readable catalogue conventions such as `llms.txt`, `AGENTS.md`/`CLAUDE.md`, and Agent Skills. These carry no merge model.

---

## 1. Karpathy's "LLM Wiki" pattern

**What it is.** On 2026-04-02 Karpathy posted an X thread titled "LLM Knowledge Bases" ([post](https://x.com/karpathy/status/2039805659525644595)). His workflow: drop raw material into `raw/`, have an LLM "compile" it into a Markdown wiki, operate on the wiki through CLI tools for Q&A and incremental improvement, and browse it in Obsidian. He says he rarely edits the wiki by hand. Two days later he published an "idea file" gist, [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) (5k+ stars and 5k+ forks on the gist). It is written to be pasted into your own coding agent, which then builds the specifics. Press coverage framed it as an architecture that "bypasses RAG" ([VentureBeat](https://venturebeat.com/data/karpathy-shares-llm-knowledge-base-architecture-that-bypasses-rag-with-an)).

**Three layers** (all from the gist):
- **Raw sources**: curated and immutable. The LLM reads them and never changes them. They are the source of truth.
- **The wiki**: a directory of Markdown written by the LLM. It holds summary pages, entity pages, concept pages, comparisons, an overview and a synthesis.
- **The schema**: a `CLAUDE.md` or `AGENTS.md` that states the conventions and the ingest, query and lint workflows. Human and LLM "co-evolve" it.

Storage is "just a git repo of markdown files", so version history comes free. In his framing Obsidian is the IDE and the LLM is the programmer.

**Operations:**
- **Ingest (the merge).** The LLM reads a new source, discusses the key takeaways with you, and writes a summary page. It then updates `index.md` and the entity and concept pages the source touches, noting where new data contradicts old claims, and appends to `log.md`. One source can touch 10–15 pages. Karpathy prefers ingesting one source at a time with a human in the loop; batch ingest is optional.
- **Query.** The LLM reads the index, drills into pages and answers with citations. Good answers "can be filed back into the wiki as new pages", so the wiki also grows from questions.
- **Lint (staleness and conflicts).** A periodic health check looks for contradictions, "stale claims that newer sources have superseded", orphan pages, concepts that have no page, missing cross-links, and gaps a web search could fill.

**Discovery.** It is two plain files, not search:
- `index.md` is a content catalogue: one link and a one-line summary per page, grouped by category, rewritten on every ingest.
- `log.md` is an append-only chronology with parseable entries such as `## [2026-04-02] ingest | Title`.

The gist says reading the index first works "at moderate scale (~100 sources, ~hundreds of pages) and avoids the need for embedding-based RAG infrastructure". For larger wikis it points at [qmd](https://github.com/tobi/qmd) (30.0k★), a local BM25 + vector search tool with LLM re-ranking and a CLI and MCP server.

**Human loop.** The human picks sources, steers the analysis, asks the questions and co-edits the schema. For team use the gist mentions "possibly with humans in the loop reviewing updates". The wiki pages themselves are LLM territory.

**Open implementations** (stars as of 2026-09):
- **[AgriciDaniel/claude-obsidian](https://github.com/AgriciDaniel/claude-obsidian) (15.2k★)** — a Claude Code plugin made of 15 skills.
  - Sources arrive through a visible inbox and are kept as immutable, content-addressed copies.
  - Source and claim "ledgers" record authority, freshness, support, contradiction, confidence and review state.
  - Parallel workers return drafts, and a single orchestrator applies them as one recoverable transaction.
  - Setup commands print a JSON plan and apply it only when handed that plan's `approved_plan_sha256`.
- **[Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) (2.4k★)** — one Agent Skill.
  - Layout: `raw/<topic>/`, `wiki/<topic>/`, `wiki/index.md` and `wiki/log.md`.
  - Ingest triages each source and "just logs it when nothing is new".
  - Lint auto-fixes index and link problems and reports the rest.
- **[atomicstrata/llm-wiki-compiler](https://github.com/atomicstrata/llm-wiki-compiler) (2.1k★)** — an npm CLI that compiles in two phases: extract concepts, then generate typed pages.
  - Every claim cites source files and line ranges, and `llmwiki lint` validates those citations.
  - It adds review queues, freshness badges and trust gates enforced in the write path.
  - It departs from Karpathy by adding hybrid retrieval (semantic + BM25 + wikilink-graph expansion), MCP serving and `llms.txt` export.
- **[lucasastorian/llmwiki](https://github.com/lucasastorian/llmwiki) (1.6k★)** — leaves your document folder untouched and adds a `wiki/` folder plus a hidden `.llmwiki/` search index.
  - Claude reads, writes and searches over MCP.
  - A nightly Claude Routine rebuilds the wiki.
  - A browser clipper captures highlights and comments together with the page.

The implementations drift toward three additions Karpathy left implicit: provenance per claim, a review or approval gate on writes, and a search index once the wiki outgrows the catalogue.

## 2. DeepWiki / Devin Wiki (Cognition)

**Mechanism.** Devin "automatically indexes your repos and produces wikis with architecture diagrams, links to sources, and summaries" ([docs](https://docs.devin.ai/work-with-devin/deepwiki)). The wiki is regenerated from the code as a whole; no page is updated by hand. Users can trigger regeneration in settings. Public DeepWikis are auto-refreshed when the repo carries a DeepWiki badge ([CognitionAI/deepwiki](https://github.com/CognitionAI/deepwiki)). A Cognition staffer described badged repos as prioritised for weekly refresh ([X](https://x.com/itsandrewgao/status/1927108352061898853)).

**Steering instead of editing.** Humans do not edit pages. They steer through `.devin/wiki.json` ([docs](https://docs.devin.ai/work-with-devin/deepwiki)):
- `repo_notes`: up to 100 notes of at most 10,000 characters each.
- `pages`: 1–30 entries (80 on Enterprise). Each has a unique `title`, a `purpose`, and optional `parent` and `page_notes`.

When `pages` is given, exactly those pages are generated, "no more, no less". The human-authored input is a table of contents plus notes, and the LLM owns the prose.

**Agent discovery.** The DeepWiki MCP server is free, needs no auth, covers public repos only, and lives at `https://mcp.deepwiki.com/mcp` ([docs](https://docs.devin.ai/work-with-devin/deepwiki-mcp)). It exposes three tools:
- `read_wiki_structure` — the topic list (a catalogue).
- `read_wiki_contents` — the pages.
- `ask_question` — a grounded answer.

Private repos go through the authenticated Devin MCP server instead.

**Open clone.** [AsyncFuncAI/deepwiki-open](https://github.com/AsyncFuncAI/deepwiki-open) (18.1k★) clones the repo, embeds it, generates the wiki and answers with RAG. It keeps state under `~/.adalflow/` (`repos/`, `databases/` for embeddings, `wikicache/`) ([README](https://github.com/AsyncFuncAI/deepwiki-open/blob/main/README.ja.md)). There is no periodic re-sync; an open issue asks for one ([#402](https://github.com/AsyncFuncAI/deepwiki-open/issues/402)).

**Lesson.** Whole-corpus regeneration sidesteps merge conflicts entirely. It works because the source (code) is authoritative and the wiki is derived. It cannot work where people also write the prose.

## 3. Obsidian + AI plugins

Obsidian's model is a folder of Markdown the user owns, with plugins that add derived state beside it.

**Smart Connections** ([brianpetro/obsidian-smart-connections](https://github.com/brianpetro/obsidian-smart-connections), 5.5k★):
- Keeps embeddings in `.smart-env/` inside the vault; the notes stay the source, and the directory can be rebuilt ([FAQ](https://smartconnections.app/smart-environment/faq/)).
- Uses a built-in local embedding model: no API key and no extra app.
- Listens to Obsidian file events to stay in sync. Changing the model needs an explicit "Re-index embeddings".
- The docs tell users of third-party sync tools to exclude `.smart-env/` to avoid sync conflicts.
- It is read-only: it surfaces related notes and semantic lookup and never rewrites notes.

**Obsidian Copilot** ([logancyang/obsidian-copilot](https://github.com/logancyang/obsidian-copilot), 7.8k★, "V4"):
- **Two search paths** ([docs](https://docs.obsidiancopilot.com/vault-search-and-indexing/)).
  - Lexical file search over words, phrases, filenames and paths, with no index.
  - Semantic search, which has moved out of the plugin into a separate local service called Miyo. Miyo re-indexes on command, when a vault is registered, and when its folder scans find changes.
- **Agent Chat** lets "opencode, Claude Code, or Codex" read the vault and do multi-step work with your approval ([docs](https://docs.obsidiancopilot.com/agent-mode-and-tools/)).
- **Edit approval.** Edits pass through a "Permission required" card that shows the proposed change. The modes are Safe, Plan (draft a plan and wait for approval before editing) and Auto.
- The trend is telling: the leading Obsidian AI plugin now hands the vault to general coding agents rather than running its own RAG.

**obsidian-git** ([Vinzent03/obsidian-git](https://github.com/Vinzent03/obsidian-git), 12.0k★):
- Handles versioning and multi-device sync: commit, pull and push every N minutes, or N minutes after the last edit, with optional pull on startup ([Features](https://github.com/Vinzent03/obsidian-git/blob/master/docs/Features.md)).
- Git history is what makes unattended AI edits recoverable in an Obsidian vault.
- An in-editor conflict resolver (keep ours / theirs / both per hunk) was merged only on 2026-09-19 ([PR #1175](https://github.com/Vinzent03/obsidian-git/pull/1175)). Before that, conflicts meant a terminal.

**MCP bridges.** [MarkusPfundstein/mcp-obsidian](https://github.com/MarkusPfundstein/mcp-obsidian) (4.4k★) talks to the Local REST API plugin. Its tools are `list_files_in_vault`, `get_file_contents`, `search` (text), `patch_content` (insert relative to a heading, block reference or frontmatter field), `append_content` and `delete_file`. Heading-anchored patching is the edit primitive, and it has no merge logic.

## 4. Basic Memory

[basicmachines-co/basic-memory](https://github.com/basicmachines-co/basic-memory) (4.0k★) is the closest shipped analogue to "Markdown the agent writes and the human edits", served over MCP.

**Format** ([knowledge format](https://docs.basicmemory.com/concepts/knowledge-format)):
- Markdown with YAML frontmatter: `title`, `type`, `permalink`, `tags`, plus any custom fields.
- Body lines follow two conventions:
  - Observations: `- [category] fact #tag (context)`. Each one is indexed separately, so search can return a single fact.
  - Relations: `relation_type [[Target]]`. A bare `[[Target]]` means `links_to`.
- A forward reference to a note that does not exist yet resolves once the note is created.
- Permalinks survive renames and moves.

**Files are truth; the index is derived.** SQLite (Postgres optional) is "a secondary index" that `bm sync` rebuilds from the files. A file watcher and per-entity checksums pick up human edits, so either side can edit ([technical info](https://docs.basicmemory.com/reference/technical-information)).

**MCP tools** ([README](https://github.com/basicmachines-co/basic-memory)):
- Notes: `write_note`, `read_note`, `edit_note`, `move_note`, `delete_note`.
- Discovery: `search_notes`, `build_context` (walks the graph from a `memory://` URL), `recent_activity`, `list_directory`.
- Schema: `schema_infer`, `schema_validate`, `schema_diff`.

**Merging.** `edit_note` supports four operations: `append`, `prepend`, `find_replace` and `replace_section`. Merging is therefore the agent's job, done one surgical edit at a time. The issue tracker shows how fragile this is:
- `append` ignores `section` ([#1594](https://github.com/basicmachines-co/basic-memory/issues/1594)).
- `replace_section` can duplicate the section instead of replacing it while reporting success ([#1531](https://github.com/basicmachines-co/basic-memory/issues/1531)).
- Joining content with a single newline breaks Markdown structure ([#1585](https://github.com/basicmachines-co/basic-memory/issues/1585)).
- The cloud service accepted a stale `expected_checksum`, so its optimistic concurrency was leaky ([#1536](https://github.com/basicmachines-co/basic-memory/issues/1536)).

**Conflicts across machines.** Cloud push and pull are additive and abort when a file differs on both sides. `--on-conflict keep-cloud|keep-local|keep-both` settles it, and keep-both writes renamed duplicates ([cloud sync](https://docs.basicmemory.com/cloud/cloud-sync)).

## 5. Mem

Mem 2.0 (2025-10-01) is the consumer version of "the AI organises it for you" ([announcement](https://get.mem.ai/blog/introducing-mem-2-0)):
- **Capture without filing.** "No decisions about where it goes… Just capture, and Mem handles the rest." Search is by meaning.
- **Suggested Collections.** On capture, the AI proposes Collections to put the note in ([Collections](https://get.mem.ai/blog/automatic-organization-with-collections)).
- **Chat edits notes.** Mem Chat "can create, edit, and organize notes for you". The open note is attached to the chat automatically and edited live, for example restructuring sections or turning a dump into a checklist ([Chat](https://get.mem.ai/features/chat)).
- **Rollback, not review.** Version history lets you "always roll back" AI edits; the safety net comes after the edit rather than before it.
- **Heads Up** proactively resurfaces related notes, for example your history with a person before a meeting.

Storage is proprietary and not file-based. There is no documented contradiction handling.

## 6. Notion AI

- **Enterprise Search** searches the workspace and connected apps (Slack, Google Drive, Jira, Teams, SharePoint/OneDrive; Gmail and Linear rolling out). It always cites sources and can be toggled per source. Business and Enterprise plans only ([help](https://www.notion.com/help/enterprise-search), [connectors](https://www.notion.com/help/notion-ai-connectors)).
- **AI Meeting Notes** (2025-05) turns meetings into pages that Notion AI can search ([release](https://www.notion.com/releases/2025-05-13)).
- **Hosted Notion MCP server** (OAuth) with 37 tools ([docs](https://developers.notion.com/docs/mcp), [tool list](https://developers.notion.com/guides/mcp/mcp-supported-tools)):
  - `notion-search` — keyword search over the workspace.
  - `notion-ai-search` — also covers connected sources.
  - `notion-fetch`, `notion-create-pages`, `notion-update-page` — read and write pages.
  - `notion-query-data-sources` — SQL over databases.
  - `notion-convert-page-to-skill`, `notion-search-skills`, `notion-download-skill` — turn pages into skills and fetch them. This is a notable move toward pages as agent-loadable knowledge.
- Updates are page-level writes. Notion documents no merge or staleness model; people curate pages by hand.

## 7. Cognee

[topoteretes/cognee](https://github.com/topoteretes/cognee) (31.0k★) is the fullest "LLM builds a knowledge structure" pipeline. The structure is a graph, not documents.

- **Pipeline.** Underneath the v1.0 verbs `remember` / `recall` / `improve` sit `add` (ingest), `cognify` (build the graph) and `search`.
- **What `cognify` does** ([docs](https://docs.cognee.ai/core-concepts/main-operations/cognify)):
  1. classifies documents;
  2. checks permissions;
  3. chunks the text;
  4. has an LLM extract entities and relationships into the graph database;
  5. writes a summary per chunk;
  6. embeds nodes and summaries into the vector store.
- **Incremental updates.** `improve()` (which replaces the legacy `memify`) "enriches an existing graph… instead of re-ingesting", checking new items against existing entities ([improve](https://docs.cognee.ai/core-concepts/main-operations/improve)).
- **Conflicts.** With `CONTRADICTION_DETECTION=true`, conflicting facts are *recorded as edges*, not resolved. `PROVENANCE_TRACKING=true` keeps where each fact came from.
- **Search.** 17 types; the default is `HYBRID_COMPLETION` (lexical + semantic + entity). Others include graph completion, chunks, lexical BM25, summaries, temporal and Cypher, plus an LLM-chosen mode ([search](https://docs.cognee.ai/core-concepts/main-operations/search)).
- **MCP.** Tools are `remember`, `recall`, `forget` and `cognify_status` ([cognee-mcp](https://github.com/topoteretes/cognee/tree/main/cognee-mcp)).
- **Human editing.** None: the graph has no human-editable form.

## 8. Khoj and AnythingLLM (index-backed assistants)

**Khoj** ([khoj-ai/khoj](https://github.com/khoj-ai/khoj), 37.5k★, AGPL-3.0):
- **Sources.** Indexes Markdown, org-mode, PDF, Word, Notion and GitHub. The Obsidian and Emacs plugins and the desktop app push files; Notion and GitHub sync in the background ([data sources](https://docs.khoj.dev/data-sources/share_your_data)).
- **Sync.** The Obsidian plugin syncs periodically and has a "Force Sync" button ([Obsidian client](https://docs.khoj.dev/clients/obsidian)).
- **Retrieval** runs in two stages ([search](https://docs.khoj.dev/features/search), [models](https://github.com/khoj-ai/khoj/blob/master/src/khoj/database/models/__init__.py)):
  - bi-encoder `thenlper/gte-small`;
  - then cross-encoder rerank with `mixedbread-ai/mxbai-rerank-xsmall-v1`.
- **Agents** bundle custom knowledge, a persona and tools ([agents](https://docs.khoj.dev/features/agents)).
- It never writes back to the notes.

**AnythingLLM** ([Mintplex-Labs/anything-llm](https://github.com/Mintplex-Labs/anything-llm), 66.4k★, MIT):
- **Workspaces.** Documents are embedded per workspace.
- **Pinning** injects a document's full text into the context window, as an explicit opt-out from chunked RAG for documents that fit or matter most ([docs](https://github.com/Mintplex-Labs/anythingllm-docs/blob/main/pages/chatting-with-documents/introduction.mdx)).
- **"Watch" (live document sync)** re-embeds a watched website, connector file or (on Desktop) local file when it changes, and updates every workspace that uses it ([docs](https://github.com/Mintplex-Labs/anythingllm-docs/blob/main/pages/beta-preview/active-features/live-document-sync.mdx)).
  - Desktop checks every 10 minutes while the app is open.
  - Docker checks hourly, for files not refreshed in 7 days.
- Updates replace the embedding; they never merge into a human document.

## 9. Hosted assistants' project knowledge

**Claude Projects** ([support](https://support.claude.com/en/articles/11473015-retrieval-augmented-generation-rag-for-projects)):
- Project knowledge is placed whole in the context window until it "approaches or exceeds" the limit.
- Past the limit, RAG switches on automatically: Claude gets a project-knowledge search tool, which allows "up to 10x more content".
- It switches back when the knowledge shrinks. There is no user toggle.
- This is the cleanest statement of the rule the field keeps rediscovering: put it all in context while it fits, and search only past that point.

**GitHub Copilot Spaces** ([concepts](https://docs.github.com/en/copilot/concepts/context/spaces)):
- A Space bundles repos, files, PRs, issues, free-text notes and uploads.
- GitHub-hosted sources "are automatically updated as they change". Uploads and free text appear to be static snapshots; the docs do not say.
- **Agent access** is through the GitHub MCP server's `copilot_spaces` toolset, which is off by default ([how-to](https://docs.github.com/en/copilot/how-tos/provide-context/use-copilot-spaces/use-copilot-spaces), [toolsets](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/configure-toolsets)):
  - `list_copilot_spaces`;
  - `get_copilot_space`, which returns the Space's content and instructions.
- **Predecessor.** Copilot knowledge bases (curated collections of repo Markdown) were retired on 2025-11-01 in favour of Spaces, with a one-click conversion ([sunset](https://github.blog/changelog/2025-08-20-sunset-notice-copilot-knowledge-bases/), [conversion](https://github.blog/changelog/2025-10-17-copilot-knowledge-bases-can-now-be-converted-to-copilot-spaces/)). GitHub moved from indexed Markdown collections to curated context bundles.

**Cursor**:
- **@Docs** crawls a docs URL you add in settings and indexes it for `@Docs` context. Staff describe the pipeline on the forum ([forum](https://forum.cursor.com/t/how-does-docs-crawling-work/264)):
  1. convert HTML to Markdown;
  2. strip navigation boilerplate with n-gram dedup;
  3. split into chunks of about 500 tokens;
  4. retrieve by embedding.
  Re-indexing is periodic, but users report stale indexes ([forum](https://forum.cursor.com/t/cursor-not-re-indexing-custom-documentation/59972)). No current official doc page describes @Docs; these points come from staff answers on the forum.
- **Rules** are `.mdc` files in `.cursor/rules/`, plus `AGENTS.md`, applied Always, Intelligently (the agent decides from the rule's description), by glob, or on @-mention ([docs](https://cursor.com/docs/context/rules)).
  - The docs advise *referencing* files rather than copying their content, to avoid staleness.

## 10. Agent-readable catalogue conventions

These carry no merge logic. They are what the field uses to tell an agent *what exists* without search.

**llms.txt** ([llmstxt.org](https://llmstxt.org/), [AnswerDotAI/llms-txt](https://github.com/AnswerDotAI/llms-txt) 2.6k★), proposed by Jeremy Howard in 2024-09:
- **Format**, in order:
  - an H1 name (the only required part);
  - a blockquote summary;
  - free Markdown;
  - H2 "file lists" of `[name](url): notes`;
  - by convention, an `## Optional` section an agent may skip.
- Each page should also exist as clean Markdown at `page.html.md`.
- **Generated, not written.** Docs platforms emit it on every deploy. Mintlify, for example, generates:
  - `llms.txt` — an index capped at 100k characters, with overflow split into sub-files;
  - `llms-full.txt` — every page's full text.
  ([Mintlify](https://www.mintlify.com/docs/ai/llmstxt)). `llms-full.txt` is a platform convention, not part of the spec.

**AGENTS.md** ([agents.md](https://agents.md/), 24.6k★):
- Plain Markdown with no required fields.
- Nested files are allowed, and the closest one to the edited file wins.
- Read by Codex, Copilot, Cursor, Gemini CLI, Jules, Zed, Aider, Devin and others.
- The site claims use in 60k+ open-source projects.

**Claude Code memory** ([docs](https://code.claude.com/docs/en/memory)):
- `CLAUDE.md` files load at launch from the working directory and its parents. Subdirectory files load when Claude reads files in that directory.
- `@path` imports expand recursively.
- `.claude/rules/*.md` with `paths:` frontmatter load only for matching files.
- **Auto memory** is the most relevant precedent:
  - `MEMORY.md` is a one-line-per-entry index, loaded every session up to 200 lines or 25 KB.
  - Topic files beside it are read on demand.
  - Near the limit, Claude is told to "merge or drop stale entries".
  - This is an index-plus-files store where the model is the curator.

**Agent Skills** ([spec](https://agentskills.io/specification), 25.7k★) use progressive disclosure:
1. The `name` (≤64 characters) and `description` (≤1024 characters) of every skill, about 100 tokens each, load at startup.
2. The body (recommended under 5k tokens and 500 lines) loads on activation.
3. `references/` files load only when needed.

The always-loaded descriptions *are* the catalogue. A skill whose body lists a knowledge tree's documents and paths turns a skill into a knowledge carrier, with no retrieval tool involved.

**Why catalogue + grep instead of vector search, for coding agents:**
- Boris Cherny (Claude Code) on X: "Early versions of Claude Code used RAG + a local vector db, but we found pretty quickly that agentic search generally works better… simpler and doesn't have the same issues around security, privacy, staleness, and reliability" ([X](https://x.com/bcherny/status/2017824286489383315); also [Pragmatic Engineer](https://newsletter.pragmaticengineer.com/p/building-claude-code-with-boris-cherny)).
- Codex CLI ships no semantic index. Its prompts steer the model to `rg`/`rg --files` ([openai/codex](https://github.com/openai/codex)), and a feature request for semantic indexing is open ([#5181](https://github.com/openai/codex/issues/5181)).
- The counterpoint is Cursor's report of 12.5% higher average accuracy from adding semantic search to its agent. Even there, the conclusion is that grep *combined with* semantic search wins ([blog](https://cursor.com/blog/semsearch)).

## 11. Ingestion: turning uploads into Markdown

Every Markdown-first knowledge base needs a converter at the door. Four families matter (stars as of 2026-09):

| Tool | Stars | Approach | Formats | Licence | MCP |
|---|---|---|---|---|---|
| [microsoft/markitdown](https://github.com/microsoft/markitdown) | 186.7k | Heuristic, on standard libraries (pdfminer/pdfplumber, mammoth, python-pptx, pandas). Optional Azure Document Intelligence and LLM image captions (PPTX/images only). Per-format pip extras. | PDF, Office, HTML, CSV/JSON/XML, images (EXIF/OCR), audio (transcription), EPUB, ZIP, YouTube | MIT | [`markitdown-mcp`](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp): one tool `convert_to_markdown(uri)`, no auth; the README advises binding to localhost |
| [docling-project/docling](https://github.com/docling-project/docling) | 67.8k | ML pipeline: layout model (Heron), TableFormer for tables, pluggable OCR (Tesseract, EasyOCR, RapidOCR, macOS Vision…). Optional VLM pipeline (Granite-Docling-258M). One lossless `DoclingDocument` → Markdown, HTML, JSON ([models](https://github.com/docling-project/docling/blob/main/docs/usage/model_catalog.md)) | PDF, Office, HTML, EPUB, images, audio, email, LaTeX, more | MIT | [`docling-mcp`](https://github.com/docling-project/docling-mcp) |
| [datalab-to/marker](https://github.com/datalab-to/marker) | 39.9k | ML: layout detection plus Surya OCR. `--use_llm` sends hard parts (cross-page tables, inline math) to an LLM. Outputs Markdown, JSON block tree, HTML, chunks | PDF, images, Office, HTML, EPUB | Code Apache-2.0; **model weights modified OpenRAIL-M** — free for research, personal use and startups under $5M, otherwise a paid licence | none |
| [infiniflow/ragflow](https://github.com/infiniflow/ragflow) DeepDoc | 91.3k (RAGFlow) | In-house vision models: OCR, 10-label layout recognition, table-structure recognition; tables rewritten as sentences. Alternative parsers: Naive (text-only), MinerU, Docling ([DeepDoc](https://github.com/infiniflow/ragflow/blob/main/deepdoc/README.md), [parsers](https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/select_pdf_parser.md)) | PDF, DOCX, Excel, PPT | Apache-2.0 | via RAGFlow |

[opendatalab/MinerU](https://github.com/opendatalab/MinerU) (80.6k★) is the other heavyweight:
- Tiered pipelines, from small ONNX models up to a VLM served by llama.cpp or vLLM.
- Outputs Markdown and JSON.
- Licence: Apache-2.0 with extra conditions.

The split is between cheap heuristic conversion (MarkItDown: fast, dependency-light, weak on scanned or complex PDFs) and model-based layout recovery (Docling, Marker, DeepDoc, MinerU: better tables and reading order, at the cost of model downloads and CPU/GPU time). Marker's weight licence is the one trap for redistribution.

## 12. Comparison

| Product | Storage | How new material merges | Staleness / conflicts | How agents discover content | Human editing |
|---|---|---|---|---|---|
| Karpathy LLM Wiki | git repo of Markdown; raw sources immutable | LLM rewrites 10–15 pages per source, notes contradictions | Periodic lint pass; git history | `index.md` catalogue + `log.md`; search only at scale | Humans curate sources and co-own the schema; the LLM owns the pages |
| claude-obsidian | Obsidian vault + ledgers | Parallel drafts → one orchestrated transaction | Per-claim freshness and contradiction ledger; hash-approved plans | Skills + index | Approval gates |
| DeepWiki | Generated wiki (hosted) | Whole regeneration from code | Weekly refresh for badged repos | MCP `read_wiki_structure` / `read_wiki_contents` / `ask_question` | Steer via `wiki.json` only |
| Obsidian + Copilot / Smart Connections | Markdown vault + `.smart-env` / Miyo index | Agent edits with per-change permission | obsidian-git history and hunk resolver | Lexical + embedding search | Full; people own the files |
| Basic Memory | Markdown + SQLite secondary index | Agent `edit_note` append / replace | Checksums; keep-local/cloud/both on sync | `search_notes`, `build_context` graph walk | Full; watcher reindexes |
| Mem | Proprietary | Chat edits the open note | Version rollback | Semantic search, suggested Collections | Full |
| Notion AI | Proprietary pages | Page-level writes | None documented | Keyword and AI search via MCP | Full |
| Cognee | Graph + vector + relational | `improve()` enriches the graph | Contradictions recorded as edges | 17 search modes | None |
| Khoj / AnythingLLM | Vector index over files | Re-embed on sync or watch | Periodic re-sync | Embedding search (+ rerank); AnythingLLM pinning | On the source files only |
| Claude Projects | Uploaded files | Replace files | — | Whole context, then automatic RAG past the limit | Re-upload |
| Copilot Spaces | Curated bundle | GitHub sources live, uploads static | Auto-updates GitHub sources | MCP `get_copilot_space` | Curate the bundle |
| llms.txt / AGENTS.md / Skills | Markdown files | n/a (generated or hand-written) | Regenerate on deploy / hand pruning | Always-loaded catalogue, then read files | Full |

## Patterns and trade-offs

- **A catalogue plus direct reads is the working answer at hundreds of documents.** Karpathy's `index.md`, `llms.txt`, Claude Code's `MEMORY.md`, skill descriptions and DeepWiki's `read_wiki_structure` are the same idea: a small, always-visible table of contents with one line per document, then the agent opens files. Claude Projects encodes the threshold explicitly (whole context while it fits, retrieval past it), and Karpathy's gist names the scale (~hundreds of pages). Coding agents' preference for grep over vector indexes points the same way.
- **Where the field splits is who owns the prose.**
  - DeepWiki and Karpathy's pure pattern give the pages to the LLM. Humans steer through a schema or `wiki.json` and never edit a page, which makes whole-page rewrites and regeneration safe.
  - Obsidian, Basic Memory and Mem give pages to both. Every one of them then needs a safety net: permission cards (Copilot), git history and a hunk resolver (obsidian-git), checksums and keep-both (Basic Memory), or version rollback (Mem).
  - No surveyed product documents a rule that an LLM merge must never revert a human's edit. Protection comes from approval before the edit or rollback after it.
- **Merge granularity.**
  - Whole-corpus regeneration (DeepWiki, Mintlify's `llms.txt`) has no conflicts but also no human prose.
  - Whole-page LLM rewrites (Karpathy) keep pages coherent but need lint and history to catch drift.
  - Surgical agent edits (Basic Memory's append/replace, mcp-obsidian's heading-anchored patch) are the most fragile in practice; they have open bugs for duplicated sections and broken Markdown.
- **Contradictions are recorded more often than resolved.** Karpathy notes them at ingest and sweeps for them in lint. Cognee writes them as graph edges. claude-obsidian keeps a contradiction ledger. The consistent instinct is to keep both claims visible, with provenance and dates, rather than silently overwrite.
- **Provenance creeps in as implementations mature.** The later Karpathy-style implementations add per-claim source citations (llm-wiki-compiler), content-addressed immutable sources (claude-obsidian) and freshness badges. Unattended rewrites erode trust quickly without them.
- **Derived indexes live beside the files and must be excluded from sync.** Smart Connections' `.smart-env/`, llmwiki's `.llmwiki/` and deepwiki-open's `~/.adalflow/` are all rebuildable sidecars. Smart Connections has to tell users to exclude its sidecar from sync to avoid conflicts.
- **Ingestion is a pluggable converter at the door.** Every Markdown-first system converts uploads once and then works on Markdown. The choice between heuristic (MarkItDown) and layout-model (Docling, Marker, MinerU, DeepDoc) converters trades install weight for quality on PDFs and tables.

## Worth borrowing / worth avoiding

**Borrow:**
- **Karpathy's ingest discipline.** Treat an ingest as a multi-page update, not a new file. Log every pass in an append-only, parseable form. "Just log it when nothing is new" (karpathy-llm-wiki) is a cheap guard against churn.
- **A lint or sweep pass separate from ingest**, looking for contradictions, stale claims, orphans and missing pages. Staleness is a property of the corpus, not of one incoming item.
- **Superseded claims kept visible with dates**, as Cognee's contradiction edges and Karpathy's "noting where new data contradicts old claims" do, rather than overwriting the old claim silently.
- **DeepWiki's steering file**: a human-owned outline and notes that bound what the LLM generates, instead of reviewing its output line by line.
- **Claude Projects' threshold rule**: whole-context delivery while the catalogue fits, retrieval only once it demonstrably does not.
- **Skills as the delivery vehicle**: an always-loaded description plus a body carrying the catalogue gets knowledge in front of an agent without a tool it has to remember to call.
- **Pluggable converters behind one interface**: MarkItDown as the light default, with a layout-model engine (Docling is MIT-licensed with an MCP server) for scanned or table-heavy PDFs.
- **Git as the recovery layer for unattended rewrites**, as in the Obsidian + obsidian-git workflow and Karpathy's "just a git repo".

**Avoid:**
- **Fine-grained agent-driven patch APIs as the only merge path.** Basic Memory's `append`/`replace_section` bugs show how easily section-level edits duplicate content or break Markdown while reporting success.
- **Opaque stores for knowledge people are meant to edit.** Cognee's graph, AnythingLLM's embeddings and Mem's proprietary store cannot be corrected with an editor, and every update is a re-ingest.
- **Retrieval tools an agent has to remember to call.** Hosted systems hide this behind automatic switching (Claude Projects). Coding agents default to their own file tools and grep.
- **Crawled-and-embedded indexes with no visible freshness.** Cursor @Docs users report re-indexing that silently does not happen, and deepwiki-open has no re-sync at all.
- **Model-weight licences with revenue caps in a redistributed binary**, such as Marker's OpenRAIL-M weights, unless the licence is cleared.

## Retrieval reference

This section is kept for reference in case ranked semantic retrieval is ever reintroduced. Every point was re-verified 2026-09.

- **Hybrid search is BM25 + dense vectors, fused by Reciprocal Rank Fusion.** The RRF score is Σ 1/(k + rank_i), with k = 60 (Cormack, Clarke & Büttcher, SIGIR 2009, [paper page](https://research.google/pubs/reciprocal-rank-fusion-outperforms-condorcet-and-individual-rank-learning-methods/)).
  - LlamaIndex's `QueryFusionRetriever(mode="reciprocal_rerank")` hard-codes k = 60 ([source](https://github.com/run-llama/llama_index/blob/main/llama-index-core/llama_index/core/retrievers/fusion_retriever.py)).
  - Alex Garcia shows RRF in SQL over FTS5 + [sqlite-vec](https://github.com/asg017/sqlite-vec) (8.1k★) ([blog](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html)).
  - FTS5's `bm25()` returns *negative* scores: more negative is better, so plain ascending `ORDER BY rank` puts the best match first ([FTS5](https://www.sqlite.org/fts5.html)).
- **Reranking with a cross-encoder** is the usual second stage:
  - Khoj defaults to `mixedbread-ai/mxbai-rerank-xsmall-v1` after a `gte-small` bi-encoder.
  - AnythingLLM's native reranker uses `Xenova/ms-marco-MiniLM-L-6-v2`, chosen as faster than mxbai on CPU and offered only with LanceDB ([source](https://github.com/Mintplex-Labs/anything-llm/blob/master/server/utils/EmbeddingRerankers/native/index.js)).
  - Open WebUI's hybrid search is off by default. It combines BM25 and vector with a 0.5 BM25 weight, and its reranker model is left empty for the user to set ([config](https://github.com/open-webui/open-webui/blob/main/backend/open_webui/config.py)).
- **Contextual retrieval.** Anthropic (2024-09) prepended an LLM-written context sentence to each chunk before embedding and BM25 indexing. The top-20 retrieval failure rate fell ([post](https://www.anthropic.com/news/contextual-retrieval)):

  | Added | Reduction | Failure rate |
  |---|---|---|
  | Contextual embeddings | −35% | 5.7% → 3.7% |
  | + contextual BM25 | −49% | 2.9% |
  | + reranking | −67% | 1.9% |
- **Embedding-model lock-in.** RAGFlow ties a dataset to its embedding model once chunks exist. Its defaults are similarity threshold 0.2 and vector weight 0.3. Since 0.22.1 an opt-in check allows a switch only if re-encoded sample chunks keep average cosine similarity ≥ 0.9 ([blog](https://ragflow.io/blog/ragflow-seamless-upgrade-from-0.21-to-0.22-and-beyond), [notes](https://github.com/infiniflow/ragflow/blob/main/docs/guides/dataset/notes_and_faqs.md)). Files-as-truth designs avoid this, because the index can be rebuilt from the files.
- **Local embeddings are universal** among self-hosted peers: Smart Connections has a built-in model, Khoj uses `gte-small`, AnythingLLM ships ONNX `all-MiniLM-L6-v2`, and qmd runs its models locally. No API dependency is needed for a semantic tier.
