# Agent memory: how other products do it

**Feature**: long-term memory for coding agents — capturing what an agent learned across sessions, consolidating it, and handing it back at session start · **Coffer spec**: [memory](../../openspec/specs/memory/spec.md) · **Related ADRs**: [aggregate-agent-memory-never-write-it](../decisions/aggregate-agent-memory-never-write-it.md), [agent-hook-installation](../decisions/agent-hook-installation.md), [coffer-model-is-an-internal-engine](../decisions/coffer-model-is-an-internal-engine.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (official docs, repository source and READMEs); star counts from the GitHub API on 2026-09-24

---

## Scope and the frame used

Every system below is described along the same seven dimensions:

1. **Write path**: who decides what gets remembered (the human, the working agent in-loop, or a background process), and from what input (explicit request, live tool events, finished transcripts).
2. **Consolidation**: whether anything merges, dedups, rewrites or retires what was captured, and when.
3. **Storage**: what the source of truth is (markdown files, JSONL, SQLite, a vector store, a graph).
4. **Retrieval**: how a stored item gets back into a model's context (always loaded, index plus on-demand read, search tool, semantic top-k).
5. **Scope**: per project, per user, global, per agent.
6. **Delivery**: pushed at session start (or every prompt) vs pulled by a tool call.
7. **Human editability**: can a person see, correct and delete what the system believes.

Products are grouped as: agent-native memory (the agents themselves), consumer assistants, memory frameworks/services, and third-party memory add-ons for coding agents. Stars are as of 2026-09.

| Product | Kind | Stars (2026-09) |
| --- | --- | --- |
| [thedotmack/claude-mem](https://github.com/thedotmack/claude-mem) | Coding-agent memory add-on | 94.6k |
| [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) (memory server is one of many) | Reference MCP servers | 90.6k |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | Memory framework + platform | 65.9k |
| [getzep/graphiti](https://github.com/getzep/graphiti) | Temporal knowledge-graph framework (Zep's core) | 31.1k |
| [topoteretes/cognee](https://github.com/topoteretes/cognee) | Graph memory engine | 31.0k |
| [rohitg00/agentmemory](https://github.com/rohitg00/agentmemory) | Coding-agent memory server | 28.8k |
| [letta-ai/letta](https://github.com/letta-ai/letta) | Stateful agent server (MemGPT) | 24.9k |
| [getzep/zep](https://github.com/getzep/zep) | Managed context-graph service | 4.9k |
| [basicmachines-co/basic-memory](https://github.com/basicmachines-co/basic-memory) | Markdown knowledge base over MCP | 4.0k |
| [letta-ai/letta-code](https://github.com/letta-ai/letta-code) | Letta's coding-agent harness | 3.4k |
| [letta-ai/claude-subconscious](https://github.com/letta-ai/claude-subconscious) | Letta background agent for Claude Code | 2.9k |
| [langchain-ai/langmem](https://github.com/langchain-ai/langmem) | LangGraph memory SDK | 1.7k |

Closed products (Claude Code, Codex, Cursor, Windsurf/Devin Desktop, ChatGPT) have no star count; the first two are open source only in part (Codex's Rust CLI is open, see below).

---

## Agent-native memory

### Claude Code

Source: [How Claude remembers your project](https://code.claude.com/docs/en/memory), [Hooks reference](https://code.claude.com/docs/en/hooks) (both checked 2026-09-24).

Claude Code has **two** memory systems, both loaded at the start of every session and both treated as context rather than enforced configuration.

**1. CLAUDE.md (human-written instructions).**

- **Locations, broadest first**: managed policy (`/Library/Application Support/ClaudeCode/CLAUDE.md` on macOS, `/etc/claude-code/CLAUDE.md` on Linux/WSL, `C:\Program Files\ClaudeCode\CLAUDE.md` on Windows; cannot be excluded by users) → user (`~/.claude/CLAUDE.md`, plus `~/.claude/rules/`) → project (`./CLAUDE.md` or `./.claude/CLAUDE.md`, checked in) → local (`./CLAUDE.local.md`, gitignored).
- **Loading**: every `CLAUDE.md`/`CLAUDE.local.md` from the working directory **up to the filesystem root** is loaded at launch and **concatenated, not overridden**; content is ordered root-first so the most specific file is read last, and within a directory `CLAUDE.local.md` follows `CLAUDE.md`. Files in **subdirectories** load lazily when Claude reads a file there. Block-level HTML comments are stripped before injection. Project-root CLAUDE.md is re-read from disk after `/compact`; nested files and path-scoped rules reload only when a matching file is read again.
- **Imports**: `@path` (relative to the importing file, or absolute) expands the target at launch, recursive to **four hops**; `@` inside code spans/fences is ignored. Imports resolving outside the working directory trigger a one-time approval dialog for project files.
- **Rules**: `.claude/rules/**/*.md`; a rule with `paths:` glob frontmatter loads only when Claude reads a matching file (`paths` is the only frontmatter field read).
- **Size**: guidance is under 200 lines per file; a CLAUDE.md up to 4 MiB loads in full, a larger one is skipped. `/doctor` proposes trims (cut what is derivable from code, keep pitfalls and rationale).
- **AGENTS.md**: since v2.1.277 Claude Code reads `AGENTS.md` directly **only when no CLAUDE.md / CLAUDE.local.md exists** on the path (setting `instructionFiles`: `claude-md-or-agents-md` default, `claude-md-and-agents-md`, `claude-md`, `managed-only`). The documented sharing idiom is a `CLAUDE.md` containing `@AGENTS.md`, or a symlink. The docs explicitly tell users to delete an older `SessionStart` hook that printed AGENTS.md, since it now produces a duplicate copy.
- **Monorepos**: `claudeMdExcludes` (glob on absolute paths, arrays merge across settings layers) skips other teams' files.

**2. Auto memory (agent-written learnings).**

- **Storage**: `~/.claude/projects/<project>/memory/`, where `<project>` is derived from the **git repository**, so all worktrees and subdirectories of one repo share one directory; outside git the project root is used. Relocatable with `autoMemoryDirectory` or `CLAUDE_CODE_PROJECT_DIR_NAME`. **Machine-local**; not synced. Excluded from the transcript retention sweep (`cleanupPeriodDays`).
- **Data model**: `MEMORY.md` is an **index, one line per memory**, plus **one topic file per memory** (e.g. `user_role.md`, `feedback_testing.md`). Topic files carry YAML frontmatter with a `type` of `user` (role, expertise, preferences), `feedback` (corrections and confirmed approaches), `project` (work, deadlines, decisions not derivable from code/git) or `reference` (where outside information lives). Since v2.1.214 Claude Code stamps a `modified` ISO-8601 field on every write to a file that has frontmatter, so both the user and the model can judge freshness.
- **Write path**: the working agent decides in-loop, "based on whether the information would be useful in a future conversation"; it skips anything derivable from the codebase and anything CLAUDE.md already says. "Remember X" from the user goes to auto memory; "add this to CLAUDE.md" goes to CLAUDE.md. The UI surfaces "Saved N memories" / "Recalled N memories".
- **Retrieval/delivery**: the first **200 lines or 25 KB** of `MEMORY.md` (whichever first) is loaded into every session; topic files are **not** loaded, the model reads them with ordinary file tools when it judges them relevant. There is no search index or embedding.
- **Consolidation**: there is no background pass. Instead the harness enforces the index budget at write time: after a write to `MEMORY.md` near a limit, Claude Code reminds the model to "keep one line per entry, move detail into topic files, and merge or drop stale entries"; over the limit the write succeeds but returns an error instructing a rewrite, because everything past the limit is dropped on next load.
- **Scope extras**: subagents do not inherit the main auto memory (forks do); a subagent can have its own memory directory via its `memory` field. Toggle with `/memory`, `autoMemoryEnabled`, or `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.
- **Human surface**: `/memory` lists every CLAUDE.md/rules location (including not-yet-existing ones) and opens the auto-memory folder in an editor; `/context` shows what actually loaded; the `InstructionsLoaded` hook logs which files loaded and why.

**The `#` shortcut.** Earlier Claude Code versions let a user start a message with `#` to append a line to a chosen memory file. The current memory page does not mention it; the documented path is now "ask Claude to remember" or edit via `/memory`. *(Removal date not verified.)*

**Hooks as an injection channel** (relevant to every add-on below): `SessionStart` (matchers `startup`, `resume`, `clear`, `compact`, `fork`) and `UserPromptSubmit` add plain stdout, or `hookSpecificOutput.additionalContext`, to the model's context as a system reminder. Each such string is **capped at 10,000 characters**; above that Claude Code writes it to a file in the session directory and passes only the path plus a 2,000-character preview, with no setting to raise the cap. Default command-hook timeout is 600 s, lowered to 30 s on `UserPromptSubmit`.

### OpenAI Codex (CLI and app)

Sources: [codex-rs/memories/README.md](https://github.com/openai/codex/blob/main/codex-rs/memories/README.md), [config types](https://github.com/openai/codex/blob/main/codex-rs/config/src/types.rs), [read-path template](https://github.com/openai/codex/blob/main/codex-rs/ext/memories/templates/memories/read_path.md), [consolidation template](https://github.com/openai/codex/blob/main/codex-rs/memories/write/templates/memories/consolidation.md), [write constants](https://github.com/openai/codex/blob/main/codex-rs/memories/write/src/lib.rs), [Codex memories docs](https://learn.chatgpt.com/docs/customization/memories?surface=app) (all checked 2026-09-24).

**Human-written instructions** are `AGENTS.md` (global in `CODEX_HOME`, then repo root down to cwd, concatenated). The memories docs say to keep critical rules there and to treat memories as "a recall layer, not the sole authority".

**Memories** are a separate, opt-in feature (`[features] memories = true` in `config.toml`, or Settings > Personalization in the app). It is the most fully engineered **transcript-distillation** pipeline among the agents, and it is open source end to end.

- **Trigger**: the pipeline runs at **root session start** (non-ephemeral, not a sub-agent, state DB available), not at session end. It works on *previous* sessions ("rollouts").
- **Phase 1, per rollout extraction**: claims eligible rollouts from the state DB (lease-based jobs, 1 h lease/retry). Defaults: a rollout must be idle at least **6 hours** (`min_rollout_idle_hours`), at most **10 days** old (`max_rollout_age_days`), **2** rollouts per startup (`max_rollouts_per_startup`, 1–128), concurrency 8, input capped around 150k tokens per rollout. Background work is skipped when rate-limit headroom is under **25%** (`min_rate_limit_remaining_percent`). Each rollout is filtered to memory-relevant items and sent to a model with a strict-schema prompt returning `raw_memory`, `rollout_summary` and optional `rollout_slug`; outputs are **secret-redacted** and stored as stage-1 rows. `disable_on_external_context` marks threads that used MCP, web search or tool search as "polluted" and excludes them.
- **Phase 2, global consolidation**: takes a **single global lock**, selects up to **256** stage-1 outputs (`max_raw_memories_for_consolidation`, 1–4096), dropping memories whose `last_usage` is older than **30 days** (`max_unused_days`) and ranking by `usage_count` then recency. It materialises `raw_memories.md` and `rollout_summaries/<slug>.md`, computes a **git-style diff** against the previous baseline (`~/.codex/memories/.git`) into `phase2_workspace_diff.md`, and, only if something changed, spawns an **internal consolidation sub-agent** with no approvals, no network and local-write-only sandbox. After success the git baseline is reset; a watermark prevents moving backwards.
- **Artifacts** in `~/.codex/memories/`: `memory_summary.md` (must start with the line `v1`; cross-task summary, "prompt-loaded context, so optimize for high signal per token"), `MEMORY.md` (the "searchable registry": `# Task Group` blocks with `## Task n`, `## User preferences`, `## Reusable knowledge`, `## Failures and how to do differently`), `rollout_summaries/`, and optionally generated `skills/<name>/SKILL.md`.
- **Consolidation rules** (from the template): INIT vs INCREMENTAL mode; order blocks by expected utility with recency as proxy; "fresher validated evidence usually wins"; "if evidence conflicts and validation is unclear, preserve the uncertainty explicitly"; hand edits that appear in the diff are "authoritative" and must be kept, not dropped. **Forgetting is evidence-driven**: when a rollout summary is pruned, the agent deletes only `MEMORY.md` content supported *solely* by that input and then rewrites the summary.
- **Delivery**: at session start the read-path template is injected as developer instructions, with `memory_summary.md` embedded and **truncated to 2,500 tokens**. The model is told to do a "quick memory pass" (grep `MEMORY.md` by keywords, open 1–2 rollout summaries, budget "≤ 4–6 search steps") and to state when an answer is memory-derived and possibly stale.
- **Usage feedback loop**: when the model uses memory it must append an `<oai-mem-citation>` block listing `file:lines|note=…` and rollout ids; these citations update `usage_count`/`last_usage`, which drive phase-2 selection and the 30-day retirement.
- **Writes by the working agent**: only on explicit user request, into `extensions/ad_hoc/notes/`, which the next consolidation folds in.
- **Scope**: a **single store under `CODEX_HOME`**, not partitioned per repository; task groups record their workspace inside the text. *(Inferred from the templates and layout; no per-project store is documented.)*
- **Human surface**: plain markdown under a git baseline; `/memories` toggles per-chat generation/use; `generate_memories` / `use_memories` switch the two halves separately. An open issue asks for official inspect/prune/delete commands ([#30299](https://github.com/openai/codex/issues/30299)).

### Cursor

Sources: [Cursor 1.0 changelog](https://cursor.com/changelog/1-0), [staff reply on removal](https://forum.cursor.com/t/are-my-memories-gone/144057), [Rules docs](https://cursor.com/docs/rules) (checked 2026-09-24).

- **Memories (June 2025 – Nov 2025)**: shipped in 1.0 (beta) as "facts from conversations", stored "per project on an individual level", managed in Settings. Secondary descriptions say a **sidecar model** watched chats and **proposed** memories that the user approved or rejected, and that the feature required Privacy Mode ([localskills write-up](https://localskills.sh/blog/cursor-memories-guide), [forum announcement](https://forum.cursor.com/t/0-51-memories-feature/98509/12)). *(Sidecar/approval flow not verified against a primary Cursor doc, which is no longer online.)*
- **Removed in 2.1.x**: a Cursor staff member confirmed on 2025-11-25 that "the Memories feature was intentionally removed starting from version 2.1.x" and pointed users to the "Export memories" command, which writes an `.mdc` file to paste into Rules. No reason was given publicly.
- **What remains is rules**: Project rules (`.cursor/rules/*.mdc`, YAML frontmatter `description`, `globs`, `alwaysApply`; a plain `.md` there is ignored), User rules, Team rules (dashboard, Team/Enterprise), and `AGENTS.md` (root and nested). Application modes: always, auto-attached by glob, agent-selected by description, manual `@`-mention. Precedence Team → Project → User. `/create-rule` drafts a rule from chat. Rules are human-authored and checked in; there is no automatic capture.

### Windsurf / Devin Desktop (Cascade)

Source: [Cascade memories & rules](https://docs.devin.ai/desktop/cascade/memories) (docs.windsurf.com now redirects here; the docs use "Windsurf" and "Devin Desktop" interchangeably), checked 2026-09-24.

- **Auto-generated memories**: "During conversation, Cascade can automatically generate and store memories if it encounters context that it believes is useful to remember"; users can also say "create a memory of …". Stored locally at `~/.codeium/windsurf/memories/`, **workspace-scoped** ("not available in another" workspace, not committed). Creating and using them consumes no credits. Viewed and edited through the Customizations panel.
- **Rules**: global `~/.codeium/windsurf/memories/global_rules.md` (always on, **6,000 characters**); workspace `.devin/rules/*.md` (preferred) or `.windsurf/rules/*.md` (legacy), **12,000 characters per file**; activation `always_on`, `model_decision` (description always shown, body fetched on demand), `glob`, `manual`. `AGENTS.md` is processed by the rules engine (root always-on, subdirectory files auto-globbed). Enterprise system rules under `/etc/devin/rules/` etc., read-only.
- No documented consolidation, dedup or retirement of auto-memories.

---

## Consumer assistant: ChatGPT

Sources: [OpenAI on X, 2025-10](https://x.com/OpenAI/status/1978608684088643709), [Dreaming announcement](https://openai.com/index/chatgpt-memory-dreaming/) (returned 403 to automated fetch; content taken from [EdTech Innovation Hub coverage](https://www.edtechinnovationhub.com/news/openai-rolls-out-new-chatgpt-memory-system-to-keep-personalization-current), 2026-06-08), [Memory FAQ](https://help.openai.com/en/articles/8590148-memory-faq) (403 to fetch).

- **Saved memories** (2024): short facts the model saves via a tool when the user asks or when it judges them durable; a user-visible list in Settings > Memory.
- **Reference chat history** (2025): the model also draws on an implicit profile built from past chats, not shown verbatim.
- **Automatic memory management** (Oct 2025, Plus/Pro): "no more 'memory full'" — the system reprioritises which saved memories stay active; users can search and sort by recency and re-prioritise manually.
- **Dreaming** (rollout began 2026-06-04, US Plus/Pro first): a **background process** re-synthesises a memory profile from past conversations and revises it over time, including time-sensitive rewrites (the widely quoted example: "You're going to Singapore in July" becomes "You went to Singapore in July 2026"). Reported evaluations: factual recall 41.5% (2024) → 82.8% (Dreaming V3), time-sensitive updates 9.4% → 75.1%, at about 5× less compute. A **memory sources** view shows which past chat, saved memory, custom instruction, file or connected app a personalised answer drew on. Users can review and edit the memory summary, turn memory off, or use Temporary Chats (neither read nor write memory); fully removing a fact requires deleting it from chats, files, the summary and connected apps. *(Numbers from secondary coverage of the OpenAI post; not re-read at source.)*

---

## Memory frameworks and services

### mem0

Sources: [add operation](https://docs.mem0.ai/core-concepts/memory-operations/add), [OSS v2 → v3 migration](https://docs.mem0.ai/migration/oss-v2-to-v3), [token-efficient algorithm post](https://mem0.ai/blog/mem0-the-token-efficient-memory-algorithm), paper [arXiv 2504.19413](https://arxiv.org/abs/2504.19413) (checked 2026-09-24). Apache-2.0, 65.9k stars.

- **The classic pipeline (paper, v1/v2)**: an LLM extracts candidate facts from the new message pair plus a rolling summary and recent messages; for each candidate the top-*s* similar existing memories are retrieved and a second LLM call (function-calling) chooses **ADD / UPDATE / DELETE / NOOP**, i.e. "latest truth wins" reconciliation at write time. `infer=False` stores raw text with no extraction or dedup.
- **v3 (April 2026) reversed this**: extraction is now a **single LLM pass that only adds**. "`add()` returns `ADD` only"; "when information changes, the new fact is stored alongside the old one", on the stated rationale that "the model spends its capacity on understanding the input rather than diffing against existing state" and that keeping history improves temporal reasoning. Conflict resolution moves to **read time**. Reported gains: LoCoMo 71.4 → 91.6, LongMemEval 67.8 → 93.4, extraction latency roughly halved (vendor numbers).
- **Retrieval (v3)**: "multi-signal hybrid search (semantic + BM25 keyword + entity matching)" fused into one score; "BM25 is a boost signal, not a recall expander" — only semantic hits are candidates.
- **Graph**: external graph-store drivers (Neo4j, Memgraph, Kuzu …, ~4,000 LOC) were **removed from the OSS SDK**; graph memory is now a Platform-only feature, replaced in OSS by built-in entity linking.
- **Scope**: `user_id`, `agent_id`, `app_id`, `run_id`; for `search()`/`get_all()` they live in a `filters` dict. Optional `metadata`, and `expiration_date` (hidden from search unless `show_expired`). Platform `add` is async (`status: "PENDING"`, poll `event_id`).
- **Human surface**: API/dashboard; no file a person edits.

### Zep and Graphiti

Sources: [Graphiti README](https://github.com/getzep/graphiti), Zep paper [arXiv 2501.13956](https://arxiv.org/abs/2501.13956), [Graphiti MCP server](https://help.getzep.com/graphiti/getting-started/mcp-server). Graphiti 31.1k stars; Zep (managed) 4.9k.

- **Data model**: a **temporal context graph** — entity nodes with evolving summaries; fact edges (entity → relation → entity) each carrying a **validity window**; **episodes** (raw ingested messages/documents) as provenance for every derived node and edge; optional Pydantic-defined entity/edge types.
- **Write path**: every episode is processed incrementally by an LLM: extract entities, resolve them against existing nodes, extract facts, then compare new facts with semantically related existing edges.
- **Conflict handling**: bi-temporal. Per the paper, edges track event time (when the fact was true, `valid_at`/`invalid_at`) and ingestion time (when the system learned/expired it). A contradicting new fact **invalidates** the old edge by closing its validity window instead of deleting it, so "what is true now" and "what was true at T" are both queryable. The README summarises this as "old facts are invalidated — not deleted". *(Field names from the paper as recalled; not re-read this pass.)*
- **Retrieval**: hybrid semantic + BM25 + graph traversal, "without reliance on LLM summarization" at query time; sub-second typical latency.
- **Storage**: bring-your-own graph DB (Neo4j 5.26, FalkorDB, Neptune; Kuzu deprecated) for Graphiti; Zep runs its own proprietary graph engine with users/threads built in.
- **Scope**: `group_id` namespaces graphs; Zep manages per-user graphs.
- **Human surface**: Zep dashboard with graph visualisation; Graphiti none.

### Letta (MemGPT), Letta Code, and claude-subconscious

Sources: [memory blocks](https://docs.letta.com/guides/agents/memory-blocks/), [Letta Code memory](https://docs.letta.com/letta-code/memory), [MemFS](https://docs.letta.com/letta-code/memfs), [letta-code README](https://github.com/letta-ai/letta-code), [claude-subconscious README](https://github.com/letta-ai/claude-subconscious) (checked 2026-09-24).

- **Memory blocks** (Letta server): labelled strings (`label`, `description`, `value`, `limit` in characters, `read_only`) **prepended to the prompt** inside `<memory_blocks>` on every call — always visible, no retrieval. The agent edits its own blocks with built-in memory tools; out-of-context "archival" memory is searched by tool. A block can be attached to several agents ("update once, visible everywhere"). Blocks live in Letta's database, not in files.
- **Sleep-time compute, now "dreaming"**: from the [sleep-time compute paper](https://arxiv.org/abs/2504.13171); a background agent shares the primary agent's blocks and rewrites them between turns. In Letta Code it is configured with `/sleeptime`: dreaming "uses background subagents to review recent conversations, consolidate useful lessons, and update memory without interrupting your active work", triggered **after N completed agent steps or on context compaction**, with an optional "Agent reviews before applying" mode where a second background conversation reviews proposed edits.
- **MemFS (Letta Code)**: memory is a **git-backed directory**: files under `system/` are loaded into the system prompt on every turn; other files stay out of context, but "the file tree itself is always in the system prompt, so directory and file names act as signposts". Files are markdown with a `description` frontmatter. "Every memory edit is committed"; memory subagents (dreaming, `/doctor`) work in **git worktrees** so they don't block the main agent; a remote can be set with `/memory-repository set git@…`. `/remember <text>` lets the agent choose placement; `/init` bootstraps memory by inspecting the repo and **prior coding sessions** (earlier docs describe it reading existing Claude Code and Codex history); `/doctor` audits placement, duplication and system-prompt token use.
- **claude-subconscious** (explicitly a demo app): a Claude Code plugin where a background Letta agent watches sessions. Four hooks: `SessionStart` (5 s: notify the agent, **clean up legacy `<letta>` content from CLAUDE.md**), `UserPromptSubmit` (10 s: inject memory/messages via stdout), `PreToolUse` (5 s: mid-workflow updates via `additionalContext`), `Stop` (async: parse the JSONL transcript, spawn a detached worker that sends it to the Letta agent, which may Read/Grep/Glob the repo and search the web). Modes: `whisper` (only the agent's messages), `full` (all blocks on the first prompt, diffs after), `off`. "Subconscious never writes to CLAUDE.md in any mode." One global agent (shared memory across all projects) by default; per-project agents via `LETTA_AGENT_ID`. Default agent keeps 8 blocks (`core_directives`, `guidance`, `user_preferences`, `project_context`, `session_patterns`, `pending_items`, `self_improvement`, `tool_guidelines`).

### LangMem

Sources: [conceptual guide](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/), [launch post](https://www.langchain.com/blog/langmem-sdk-launch). 1.7k stars; last commit 2026-09-09.

- **Memory types**: semantic as **collections** (many documents, unbounded) or **profiles** (one schema-shaped document updated in place, `enable_inserts=False`); **episodic** (successful interactions as few-shot examples); **procedural** (`create_prompt_optimizer` rewrites the system prompt from feedback).
- **Consolidation**: `create_memory_manager` receives the conversation **and the current memories** and prompts an LLM "to determine how to expand or consolidate the memory state" — inserting, updating, or deleting/invalidating (toggles such as `enable_inserts`, `enable_deletes`). Same shape as mem0's pre-v3 reconciliation.
- **Timing**: "hot path" (agent calls a `create_manage_memory_tool` in-loop, adds latency) vs **background** ("subconscious" formation after the interaction, e.g. via a delayed reflection executor so a burst of messages is processed once).
- **Storage/scope**: LangGraph `BaseStore`, hierarchical namespaces with templates like `("memories", "{user_id}")`; retrieval by key, semantic search, or metadata filter.

### Cognee

Sources: [README](https://github.com/topoteretes/cognee), [improve](https://docs.cognee.ai/core-concepts/main-operations/improve), [Claude Code plugin](https://github.com/topoteretes/cognee-integrations/tree/main/integrations/claude-code). Apache-2.0, 31.0k stars; v1.6.0 on 2026-09-18.

- **Operations**: `remember` (store text/code in permanent memory, or in a session when a session id is given), `recall` (routed or chosen search strategy), `improve`, `forget`. Text becomes entities, relationships and searchable chunks; code becomes a symbol/dependency graph. v1.6 builds and searches text memory with local models and no cloud LLM key; LLM-dependent stages skip.
- **Consolidation (`improve`)**: nine staged steps (apply feedback, persist session Q&A and agent traces, extract session context, **distil lessons**, update preferences, build a "truth subspace", enrich triplets, index global context). Distillation: a curator picks candidate lessons from a session, a writer validates them against existing knowledge, and accepted lessons are written as **standalone markdown** and re-ingested under `session_learnings`. Ratings adjust a per-element `feedback_weight` used in ranking.
- **Coding-agent delivery**: the Claude Code plugin (and a Codex sibling sharing `~/.cognee/.env`) captures prompts, tool traces and responses into session memory, **injects relevant context on prompt submit**, and syncs session memory into graph memory at session end. Local mode boots a Cognee API on `localhost:8011`.

---

## Memory add-ons for coding agents

### claude-mem

Sources: [README](https://github.com/thedotmack/claude-mem), [hooks architecture](https://docs.claude-mem.ai/hooks-architecture), [database](https://docs.claude-mem.ai/architecture/database) (checked 2026-09-24). Apache-2.0, 94.6k stars — the most-starred project in this survey.

- **Capture**: Claude Code plugin with lifecycle hooks. `UserPromptSubmit` (60 s) creates the session row, stores the raw prompt, auto-starts the worker. `PostToolUse` (120 s) **enqueues** tool name, input, output and timestamp to the worker and returns immediately. `Stop` (120 s) sends accumulated observations to a Claude Agent SDK session that produces a structured summary (request, investigated, learned, completed, next steps, files read/modified). `SessionEnd` marks completion and lets the worker drain.
- **Compression**: the worker turns raw tool events into typed **observations** (`decision`, `bugfix`, `feature`, `refactor`, `discovery`, `change`) with `title`, `facts`, `narrative`, `concepts`, `files_read`, `files_modified`. LLM provider is selectable: the hosted "claude-mem observer" (sign-in, free 30 days), OpenRouter/Gemini keys, or the user's Anthropic plan.
- **Storage**: `~/.claude-mem/claude-mem.db` (bun:sqlite, WAL): `sdk_sessions`, `observations`, `session_summaries`, `user_prompts`, each with an FTS5 mirror kept in sync by triggers; optional Chroma vectors for hybrid search. Optional cloud sync.
- **Delivery**: `SessionStart` injects a **progressive-disclosure index**: the last 10 session summaries and (default) 50 observations (`CLAUDE_MEM_CONTEXT_OBSERVATIONS`) as a table of ID, time, type, title and **token cost**, with a note pointing at the search tools. The model then pulls detail through 4 MCP tools in a three-step pattern: `search` (compact index, ~50–100 tokens/hit) → `timeline` (neighbouring context) → `get_observations` (full records, ~500–1,000 tokens each).
- **Worker**: Bun/Express on port `37700 + (uid % 100)` (override `CLAUDE_MEM_WORKER_PORT`), web viewer, auto-restart; DB lock → skip the observation and log; network → exponential backoff.
- **Privacy**: `<private>…</private>` spans are excluded from storage.
- **Multi-agent**: installers for OpenCode, Antigravity, OpenClaw, and a log-watching mode for hosts without hooks. One pilot writes dated "awareness" lines into another bot's own log file — the only native-file write documented.
- **Consolidation/retirement**: none documented; observations accumulate and retrieval does the filtering.

### agentmemory (rohitg00)

Source: [README](https://github.com/rohitg00/agentmemory) (checked 2026-09-24). Apache-2.0, 28.8k stars.

- **Architecture**: a local server built on the iii engine (pinned v0.22.1): REST/MCP on `:3111`, streams `:3112`, viewer `:3113`, worker WebSocket `:49134`; state under the platform data dir. One server shared by Claude Code, Codex, Cursor, Gemini CLI, Copilot CLI, OpenCode, Hermes, etc.; `agentId` threads through save/recall in shared or isolated mode.
- **Capture pipeline**: `PostToolUse` → SHA-256 dedup in a 5-minute window → secret/`<private>` stripping → store raw observation → compression (synthetic by default; LLM-written only with a provider and `AGENTMEMORY_AUTO_COMPRESS=true`) → BM25 index (+ vectors if an embedding provider, e.g. local `all-MiniLM-L6-v2`). `Stop`/`SessionEnd` → session summary, optional graph extraction and "slot reflection".
- **Delivery**: `SessionStart` loads a project profile (top concepts, files, patterns), runs hybrid search (BM25 + vector + graph, RRF-fused), and injects within a **2,000-token budget**; `PreCompact` re-injects before compaction.
- **Consolidation**: a "4-tier" model — working (raw observations) → episodic (session summaries) → semantic (facts/patterns) → procedural (workflows); Ebbinghaus-style decay, access strengthening, TTL expiry, "contradiction detection", importance eviction; superseded versions leave the search indexes but stay in a version chain. `memory_consolidate` runs it on demand. *(Decay and contradiction mechanics are README claims; the algorithm was not read in source.)*
- **Native-file bridge**: "bi-directional sync with MEMORY.md" for Claude Code only (`memory_claude_bridge_sync`).
- **Hook install lesson** in its own README: wiring hooks by absolute path into `~/.claude/settings.json` or `~/.codex/hooks.json` embeds a versioned path, "so the next upgrade silently breaks every hook"; `agentmemory connect <agent> --with-hooks` rewrites only its own entries and must be re-run after upgrades. It also documents that Codex Desktop builds do not dispatch plugin-local `hooks.json` ([openai/codex#16430](https://github.com/openai/codex/issues/16430)).

A different, much smaller project with the same name, [jayzeng/agentmemory](https://github.com/jayzeng/agentmemory) (23 stars), keeps a central markdown store in `~/.agent-memory/` and installs the same `SKILL.md` into each agent so it pulls through a CLI; it states that it complements rather than writes `CLAUDE.md`/`AGENTS.md`.

### basic-memory

Source: [README](https://github.com/basicmachines-co/basic-memory) (checked 2026-09-24). AGPL-3.0, 4.0k stars; paid cloud tier.

- **Storage**: plain markdown files (default `~/basic-memory`, config in `~/.basic-memory/`) are the source of truth, with a local SQLite index (Postgres optional) for full-text + FastEmbed vector hybrid search and optional cross-encoder rerank.
- **Grammar**: each file is an Entity; `## Observations` lines are `- [category] fact`; `## Relations` lines are `- relation_type [[Other Entity]]` wikilinks. The graph is emergent from links.
- **Tools (MCP)**: `write_note`, `read_note`, `edit_note`, `move_note`, `delete_note`, `view_note`, `search_notes`, `build_context` (follows `memory://` URLs and relations), `recent_activity`; each annotated with MCP read-only/destructive hints.
- **Write path**: the agent writes notes explicitly through tools during chat; humans edit the same files in any editor or Obsidian and sync picks it up. No automatic capture or LLM consolidation.
- **Delivery**: pull only (the agent calls `build_context` / `recent_activity` when prompted to "continue").

### Official MCP memory server

Source: [src/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) (`@modelcontextprotocol/server-memory`), checked 2026-09-24.

- **Storage**: a single **JSONL** file (`memory.jsonl` next to the package by default, `MEMORY_FILE_PATH` to override; old `memory.json` auto-migrated).
- **Model**: entities (`name`, `entityType`, `observations[]`), directed relations in active voice, observations as atomic strings.
- **Tools**: `create_entities` (ignores existing names), `create_relations` (skips duplicates), `add_observations` (drops exact duplicates via `includes`), `delete_entities` (cascades relations), `delete_observations`, `delete_relations`, `read_graph`, `search_nodes`, `open_nodes`.
- **Retrieval**: `search_nodes` is **case-insensitive substring** over names, types and observations; no ranking.
- **Consolidation/conflict**: exact-string dedup only; no LLM. Delivery is whatever the client's system prompt tells the model to do (the README suggests "remembering…" instructions in the prompt).

---

## Cross-cutting topics

### Session-start injection via hooks

Three delivery shapes exist, often combined:

- **Always-loaded file, capped** — Claude Code's first 200 lines / 25 KB of `MEMORY.md`; Letta's `system/` files and blocks; Windsurf always-on rules (6k/12k chars). Cheap, deterministic, no hook needed, but a hard ceiling that someone must keep the content under.
- **Index + on-demand read** — the Claude Code topic files, the Codex `memory_summary.md` (2,500 tokens) plus grep over `MEMORY.md`, claude-mem's table of titles with token costs, Letta's always-visible MemFS tree. The model sees *what exists* and pays for detail only when relevant. This is the pattern the three largest coding-memory designs converged on independently.
- **Search-then-inject by a hook** — agentmemory (2,000-token budget, hybrid search at `SessionStart`), Cognee (relevant context on each prompt), claude-subconscious (agent-written "whispers" on each prompt and before tool use). Relevance is computed outside the model, so it depends on the query being known — at `SessionStart` there is no user prompt yet, which is why several of these re-inject on `UserPromptSubmit`.

Practical constraints documented by the hosts: Claude Code caps each hook injection at **10,000 characters** (overflow becomes a file path + 2,000-char preview); `UserPromptSubmit` hooks default to a 30 s timeout; hooks written by absolute path into user settings break silently on upgrade (agentmemory); Codex Desktop did not dispatch plugin-local hooks at the time of writing; and Claude Code's own docs warn that a `SessionStart` hook printing a file that the agent now loads natively produces a duplicate.

### LLM consolidation and retirement of stale facts

| Approach | Who | When it runs | How stale facts leave |
| --- | --- | --- | --- |
| Write-time reconcile (ADD/UPDATE/DELETE/NOOP) | mem0 ≤ v2, LangMem memory manager | On every add | LLM decides to update/delete the similar old fact |
| Append-only, resolve at read | mem0 v3 | — | Never deleted; newer fact coexists, retrieval/temporal context decides; optional `expiration_date` |
| Temporal invalidation | Zep/Graphiti | On every episode | Old edge's validity window closed; still queryable historically |
| Batch rewrite of a curated file by a sub-agent | Codex phase 2, Letta dreaming, ChatGPT Dreaming | Background: session start after 6 h idle (Codex); every N steps or on compaction (Letta); periodic (ChatGPT) | Rewritten out; Codex deletes only content whose *supporting evidence* was pruned |
| Usage-based expiry | Codex (30 days unused, driven by citations), agentmemory (decay + access strengthening, TTL) | At consolidation | Unused items drop out of selection |
| In-loop hygiene nudges | Claude Code | When `MEMORY.md` nears 200 lines / 25 KB | The working model is told to merge or drop stale entries |
| None (human only) | Windsurf auto-memories, Cursor rules, basic-memory, MCP memory server, claude-mem | — | Manual edit/delete |

Notable details: Codex keeps a **git baseline** of its memory folder and feeds the consolidator a diff, so the sub-agent works incrementally and treats human edits as authoritative; Letta runs its memory subagents in **git worktrees** for the same reason. mem0's move to ADD-only is a deliberate retreat from write-time LLM reconciliation, justified by benchmark gains on temporal questions.

### Conflict handling

- **Latest wins, destructively**: mem0 ≤ v2, LangMem (LLM chooses update/delete).
- **Latest wins, history kept**: Graphiti (invalidate, don't delete), agentmemory (supersession chain), Letta/Codex (git history of the memory folder).
- **Both kept, flagged**: Codex's consolidation prompt — "fresher validated evidence usually wins", but "if evidence conflicts and validation is unclear, preserve the uncertainty explicitly".
- **Both kept, unflagged**: mem0 v3 and every system without consolidation; the reader model sees contradictions side by side. Claude Code's docs warn that with two contradicting instructions "Claude may pick one arbitrarily".
- **Freshness as metadata the model can see**: Claude Code's `modified` frontmatter; Codex's `updated_at` and the instruction to label memory-derived answers as possibly stale; ChatGPT's memory sources.

### Human review and edit surfaces

- **Files you open in an editor**: Claude Code (`/memory`, `/context`, `InstructionsLoaded` hook), Codex (`~/.codex/memories/*.md` under git), Letta Code MemFS (git repo, remotable), basic-memory (Obsidian-compatible), Windsurf (Customizations panel over local files), MCP memory server (JSONL).
- **Approval before save**: Cursor's former memories (per secondary sources), Letta's optional "Agent reviews before applying" (a model reviewing, not a human).
- **Dashboards/viewers over a DB**: claude-mem web viewer, agentmemory viewer (`:3113`, KV browser, hook replay), Zep dashboard, ChatGPT Settings > Memory (edit summary, see sources).
- **Nothing**: mem0 OSS and LangMem expose APIs only.
- Codex users have an open request for official inspect/prune/delete commands, a sign that plain files alone are not felt to be a sufficient management surface.

### Per-project vs global scoping

- **Per repository, derived from git**: Claude Code auto memory (all worktrees share one directory), Windsurf auto-memories (per workspace), Cursor's former memories (per project).
- **One global store**: Codex memories (single `CODEX_HOME/memories`, task groups carry the workspace), claude-subconscious (one agent brain across all projects unless `LETTA_AGENT_ID` is set per directory), ChatGPT (per account, with separate Projects).
- **Hierarchical files, concatenated**: Claude Code CLAUDE.md (managed → user → project → local, plus subdirectories), Cursor rules (Team → Project → User), Windsurf rules (system → global → workspace), AGENTS.md everywhere.
- **Identifier namespaces**: mem0 (`user_id`/`agent_id`/`app_id`/`run_id`), LangMem (namespace tuples with templates), Graphiti (`group_id`), agentmemory (`agentId`, shared or isolated; "team memory" namespaces).

---

## Summary comparison

| System | Write path | Consolidation | Storage | Retrieval | Scope | Delivery | Human edit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Code auto memory | Working agent, in-loop | In-loop nudges at index limits | Markdown index + topic files | Index loaded; topics read on demand | Per git repo, machine-local | Push (index) + pull (files) | Files, `/memory` |
| Claude Code CLAUDE.md | Human (or agent on request) | Manual; `/doctor` trims | Markdown hierarchy | Loaded in full; subdirs lazy | Managed/user/project/local | Push | Files |
| Codex memories | Background extraction from past sessions | Two-phase: per-rollout extract, global sub-agent rewrite; 30-day unused expiry | Markdown under git baseline + state DB | 2.5k-token summary + grep | Global | Push (summary) + pull (grep) | Files; `/memories` toggle |
| Cursor (now) | Human rules; `/create-rule` | None | `.mdc` + AGENTS.md | Always / glob / agent-selected / manual | Team/project/user | Push | Files |
| Windsurf / Devin Desktop | Agent auto-memories + human rules | None documented | Local files | Rules by activation mode | Workspace; global rules | Push | Panel |
| ChatGPT | Model + background Dreaming | Background re-synthesis, time-aware rewrites | Opaque | Implicit profile + saved list | Account | Push | Settings, sources view |
| mem0 v3 | LLM single-pass extraction | None at write (ADD-only) | Vector store (+ Platform graph) | Semantic, BM25/entity boosts | `user/agent/app/run_id` | Pull (search) | API |
| Graphiti / Zep | LLM extraction per episode | Temporal invalidation | Graph DB | Semantic + BM25 + traversal | `group_id` / per user | Pull | Zep dashboard |
| Letta / Letta Code | Agent self-edit, `/remember`, `/init` | Dreaming sub-agents (N steps / compaction) | DB blocks; MemFS git repo | `system/` always in prompt; tree as signposts | Per agent (shareable blocks) | Push | Files/ADE |
| claude-subconscious | Background Letta agent reads transcripts | Agent-managed blocks | Letta server | Agent chooses what to whisper | One global agent by default | Push per prompt/tool | ADE |
| LangMem | Hot path tool or background manager | LLM insert/update/delete | LangGraph BaseStore | Key / semantic / filter | Namespaces | Pull | API |
| Cognee | Hooks capture sessions; `remember` | `improve`: lesson distillation, feedback weights | Graph + vector (+ Postgres option) | Routed graph/vector search | Datasets, sessions | Push per prompt (plugin) | Graph viewer |
| claude-mem | Hooks capture every tool call | Per-session LLM summary; no retirement | SQLite + FTS5 (+ Chroma) | Index at start; 3-step search tools | Per project | Push (index) + pull (MCP) | Web viewer |
| agentmemory | Hooks capture, dedup, compress | 4-tier, decay, supersession | iii KV + BM25/vector/graph | Hybrid RRF | `agentId`, teams | Push (2k tokens) + pull | Viewer |
| basic-memory | Agent writes notes via tools | None | Markdown + SQLite index | FTS + vector hybrid | Projects | Pull | Files, Obsidian |
| MCP memory server | Agent writes via tools | Exact-string dedup | One JSONL file | Substring | Per file | Pull | JSONL |

---

## Patterns and trade-offs

- **The field converged on "index pushed, body pulled".** Claude Code (`MEMORY.md` + topic files), Codex (`memory_summary.md` + grep `MEMORY.md`), Letta Code (file tree in prompt, `system/` loaded), and claude-mem (a titled table with token costs, then search tools) all hand the model a compact map at session start and let it read detail on demand. Pure pull (basic-memory, MCP memory server, mem0 search) depends on the model deciding to look; pure push of full content does not scale past a few hundred lines.
- **Consolidation moved off the write path and into the background.** The early framework pattern — reconcile every fact with an LLM as it arrives — is being abandoned (mem0 v3 is ADD-only) or reserved for small profiles (LangMem). The agent-native systems that consolidate at all (Codex, Letta, ChatGPT) do it as a periodic batch rewrite by a sandboxed sub-agent over a whole curated file, where the model can see context and trade-offs.
- **Transcripts vs live events vs explicit saves.** Codex and claude-subconscious read finished transcripts after the fact; claude-mem, agentmemory and Cognee capture live hook events; Claude Code, Windsurf and basic-memory rely on the working agent choosing to save. Transcript/event capture has high recall and needs heavy compression and privacy filtering (secret redaction in Codex, `<private>` tags in claude-mem/agentmemory, the "polluted" flag for sessions that used external context in Codex). Explicit saves are cheap and legible but miss what the agent did not think to note.
- **Retirement needs a usage or evidence signal.** The two systems with principled forgetting tie it to something observable: Codex to citations (`usage_count`, 30 days unused) and to the survival of supporting evidence; Graphiti to explicit contradiction (validity windows). Decay curves without a usage signal are rarer and harder to verify.
- **History is kept even when the view is rewritten.** Codex and Letta commit the memory folder to git; Graphiti invalidates rather than deletes; agentmemory keeps supersession chains. Destructive "latest wins" survives mainly in small SDKs.
- **Where the field splits: files vs databases.** The agents themselves (Claude Code, Codex, Letta Code, Windsurf, Cursor) all store memory as markdown on disk that a human can open; the frameworks and most add-ons store it in SQLite, vector or graph databases with a viewer on top. Files win on trust and editability; databases win on search and on multi-writer concurrency, which the file systems solve with locks (Codex phase-2 lock) or git worktrees (Letta).
- **Where the field splits: per-repo vs global.** Claude Code and Windsurf scope memory to the repository automatically; Codex and claude-subconscious keep one global brain and rely on the text to say which workspace a lesson came from. Per-repo scoping avoids cross-project bleed; global scoping carries user preferences everywhere without duplication.
- **Third parties inject; they rarely write the agent's own files.** claude-subconscious removed its earlier CLAUDE.md writes and now only injects via hooks; jayzeng/agentmemory states it complements rather than edits CLAUDE.md/AGENTS.md; claude-mem writes native files only in one pilot. agentmemory's single-target MEMORY.md bridge is the notable exception.
- **Native memory keeps getting renamed, moved and removed.** Cursor shipped and removed memories in five months; Claude Code dropped the `#` shortcut from its docs, added AGENTS.md reading, and moved the auto-memory index limits into harness-enforced errors; Windsurf moved rule paths from `.windsurf/` to `.devin/`; Codex memories are still behind a feature flag with a `version` selector. Anything reading these formats is reading a moving target.

## Worth borrowing / worth avoiding

**Worth borrowing**

- **A one-line-per-entry index with a hard, enforced budget** (Claude Code's 200 lines / 25 KB with a write-time error; Codex's 2,500-token summary). The enforcement at write time, not silent truncation at read time, is what keeps the index honest.
- **Topic-per-file bodies with typed frontmatter and a machine-stamped `modified` time** (Claude Code), so freshness is visible to both human and model.
- **Consolidation by a sandboxed sub-agent over a git-diffed workspace** (Codex): incremental, auditable, rolls back cleanly, and lets the prompt say "user edits in this diff are authoritative".
- **Evidence-linked forgetting**: delete a remembered claim only when every input that supported it is gone (Codex), and keep a record of what was retired.
- **Usage feedback from citations**: have the model cite which memory lines it used, and use that to rank and expire (Codex `<oai-mem-citation>`).
- **Preserve conflicting evidence explicitly** rather than silently picking a winner when validation is unclear (Codex), and tell the model to label memory-derived answers as possibly stale.
- **Show token cost next to each index entry** so the model can decide what to open (claude-mem's progressive disclosure).
- **Idle-gated, rate-limit-aware background work** (Codex: 6 h idle, skip under 25% headroom) so memory never competes with the user's own session.
- **Privacy gates before storage**: secret redaction, `<private>` spans, and excluding sessions that ingested external content.
- **Marker-scoped hook installation that rewrites only its own entries** and is re-run on upgrade (agentmemory's `connect --with-hooks`), because absolute, versioned hook paths break silently.

**Worth avoiding**

- **Write-time LLM reconciliation of every fact**: expensive, lossy, and mem0 itself measured it losing to append-and-resolve-later on temporal questions.
- **Unbounded capture without retirement** (claude-mem-style accumulation): recall stays fine while search is good, but the store only grows and nothing ever says a fact stopped being true.
- **Injection that ignores the host's caps**: a `SessionStart` payload over Claude Code's 10,000-character limit arrives as a file path the model is not told to read.
- **Duplicating what the agent already loads**: a hook that prints a file the agent now reads natively (the AGENTS.md case) doubles the tokens and can drift.
- **Writing into another tool's memory files**: the add-on that did so (claude-subconscious's early `<letta>` blocks in CLAUDE.md) backed it out and now cleans it up on start.
- **Depending on an unstable native format without a visible failure**: Cursor's memories vanished in a minor release; a reader that silently returns nothing after such a change is worse than one that errors.
- **One global brain for everything by default** when lessons are repository-specific; without a workspace key the consolidator has to infer scope from prose.
