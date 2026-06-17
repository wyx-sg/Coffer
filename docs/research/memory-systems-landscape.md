# Memory Systems Landscape — How Mainstream AI Agent Memory Is Built

> 中文版: [memory-systems-landscape.zh.md](./memory-systems-landscape.zh.md)

**Type**: Research note (competitive landscape)
**Date**: 2026-06-17
**Purpose**: Benchmark Coffer's memory design ([spec 007](../../specs/007-memory/spec.md), [ADR-012](../decisions/ADR-012-files-as-truth-sqlite-retrieval.md), [ADR-013](../decisions/ADR-013-agent-native-shared-memory.md)) against how the rest of the field builds agent memory, to judge whether Coffer's choices are sound and whether its "shared memory + native projection" claim of novelty holds.
**Method**: `deep-research` harness, three rounds. **Round 1** (broad landscape) — 5 angles, 23 sources, 25 claims verified (23 confirmed / 2 killed). **Round 2** (focused novelty check) — claude-mem **vote-verified**; Letta / agentmemory / Zep extracted but rate-limited. **Round 3** (re-verify the rate-limited three) — Letta (18 unanimous 3-0 claims) and `jayzeng/agentmemory` (6 unanimous) **vote-verified**; `rohitg00/agentmemory` and Zep/Graphiti were **not vote-covered** (budget-dropped) and stay at round-2 primary-source level. Confidence labels below carry these distinctions.

---

## TL;DR

The field splits cleanly into **two camps**, and Coffer is a deliberate **hybrid** of both:

- **Camp A — Framework / library memory services** (mem0, Letta, Zep/Graphiti, Cognee, LangMem): a **vector store (or knowledge graph) is the source of truth**; the **write path runs an LLM** to extract salient facts and to dedup/reconcile (add / update / delete / noop); retrieval is **vector semantic search**; scope is by **identifier namespace** (`user_id` / `agent_id` / `run_id` / `block_id`); human review is **weak** (mostly automatic).
- **Camp B — Product-native file memory** (Claude Code, Cursor, Windsurf, ChatGPT): **local plain files (markdown) are the source of truth**, no vector store or SQL; the write path is **direct** (user hand-writes, or the agent writes plain notes — **no extraction/dedup pipeline**); retrieval is **load-the-file / tree-walk, not semantic**; scope is an **explicit file hierarchy** (managed-policy > user > project > local); human review is **strong** (files are editable and git-diffable).

**Where Coffer sits**: Coffer takes Camp B's _files-as-truth + no-LLM-at-write-time + human-curatable_ spine, then bolts on **Camp A-grade retrieval** (FTS5/BM25 + sqlite-vec semantic search — which Camp B notably _lacks_), and adds a **cross-agent shared store projected into each agent's native location**.

**Novelty verdict (firmed — high).** Decompose the claim into three parts, because they have very different novelty:

1. _**Multiple agents sharing one store**_ — **not novel.** Letta's shared memory blocks, the official MCP memory server, mem0's platform, claude-mem, and agentmemory all expose a shared central store that several agents read/write.
2. _**Projecting memory into a native file**_ — **exists, but only single-target (Claude-only).** claude-mem auto-generates one generic `CLAUDE.md` timeline file; `rohitg00/agentmemory` reportedly has a single-target "Claude bridge". Neither fans out to a second agent's native format.
3. _**Multi-target native fan-out**_ — one canonical store projected into _each heterogeneous agent's own native memory location_ (symlink where the format matches, managed block where it doesn't, the agent's native memory disabled to prevent divergence) — **found in no system across three rounds.**

So Coffer's novelty narrows precisely to part 3: the **multi-target native-projection fan-out** — _not_ the sharing (common) and _not_ the existence of native projection (single-target precedents exist). _Confidence: **high.** The three strongest candidate precedents are all now vote-verified as central-store / injection / pull models rather than fan-out: **claude-mem** (round 2), **Letta** (round 3, 18 unanimous claims), and **`jayzeng/agentmemory`** (round 3, 6 unanimous). The two remaining systems — `rohitg00/agentmemory` and Zep/Graphiti — were not vote-covered in round 3 (Caveat 1), but both are low-risk: a Claude-only bridge is still single-target, and Zep is architecturally a central KG service (the opposite of fan-out)._

> **A telling data point.** Letta — a sophisticated player — ships its own Claude Code integration (`claude-subconscious`) that **deliberately injects context via stdout and explicitly "never writes to `CLAUDE.md`"**, even actively cleaning legacy `<letta>` content out of it. The industry default is _runtime injection_, and writing into the user's native files is a path others have considered and **avoided**. That makes Coffer's projection genuinely distinctive — and is also a yellow flag worth understanding (see "Reading the field back onto Coffer", point 4).

---

## The two camps, by dimension

### 1. Storage model — who is the source of truth

| Camp                   | Source of truth                                                                                                                                                                                                          | Notes                                                                                                                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A (frameworks)**     | **Vector DB** (mem0 base: dense embeddings); **graph DB** for variants (Mem0^g: Neo4j; Zep/Graphiti: temporal KG); **relational DB** for Letta (blocks in Postgres/pgvector, compiled into the prompt at runtime).       | The official **MCP memory server** is the exception: a single local **JSONL knowledge-graph file** (`memory.jsonl`), no vector/SQL at all.                                                   |
| **B (product-native)** | **Local plain markdown files**, no vector/SQL. Claude Code: `CLAUDE.md` / `CLAUDE.local.md` + auto-memory (`MEMORY.md` + topic files). Cursor: `.cursor/rules/*.mdc`. Windsurf Cascade: `~/.codeium/windsurf/memories/`. | Every vector/SQLite add-on for these agents (MemSearch, claude-mem, Vector Memory MCP) is explicitly a _third-party overlay on top of_ the native files — confirming files are the baseline. |

_Confidence: high (3-0)._

### 2. Write path — LLM extraction + dedup, or direct write

- **Camp A: LLM at write time.** mem0's add pipeline (a) extracts salient facts from a message pair + a rolling conversation summary + a recency window, then (b) for each fact retrieves the top-_s_ semantically similar existing memories and asks an LLM (via function-calling) to classify the op as **ADD / UPDATE / DELETE / NOOP** — "latest truth wins". This is **gated by `infer=True`** (the default); with `infer=False` raw text is stored verbatim and **duplicates accumulate**. _Caveat from the field:_ mem0 issue #4896 shows that on semantically-close contradictory facts the dedup can degrade to MD5-hash matching and ADD both — so even the LLM path is not robust at the edges.
- **Camp B: direct write, no extraction/dedup.** Two sub-paths: **user-written** rules (`CLAUDE.md`, Cursor rules, Windsurf rules — no LLM) and **agent-written** auto-memory (Claude Code writes "notes … based on whether the information would be useful in a future conversation"; Cascade "automatically generate and store memories if it encounters context it believes is useful"). **Both auto-paths still write plain markdown notes — no embedding/dedup pipeline.** The MCP memory server likewise does **exact-string dedup only** (`create_entities` / `add_observations` use `===`/`includes`), zero LLM.
- **ChatGPT** is a product-layer hybrid: "Saved memories" (user-prompted facts, stored ~verbatim via the bio tool) + "reference chat history" (LLM builds an implicit profile, non-verbatim), with automatic LLM curation that weighs recency/topic-frequency to "reduce stale or contradictory saved memories".

_Confidence: high (3-0) on the mechanism existence; the user-vs-LLM dichotomy has gray zones — two claims were killed asserting a clean split (ChatGPT saved memories can be LLM-added; Cursor rules can be background-generated)._

### 3. Retrieval

- **Camp A: vector / graph semantic search.** mem0 base = dense-embedding similarity; Mem0^g and Zep/Graphiti add entity-centric graph traversal + semantic matching; Letta compiles blocks into the prompt by `block_id`. Even mem0's newer v3 hybrid (BM25 + entity) uses those only as **re-rank boosters** — vector is still the sole candidate-generation path.
- **Camp B: no semantic retrieval.** Claude Code loads in-scope `CLAUDE.md` **in full at launch**, subdirectory files **on demand**, and auto-memory loads only the **first 200 lines / 25 KB of `MEMORY.md`** (rest read on demand). The MCP server does **case-insensitive substring + exact-name** lookup (`search_nodes` / `open_nodes`). **No embeddings anywhere in Camp B's native path.**

_Confidence: high (3-0)._

### 4. Scope & namespacing

- **Camp A:** identifier namespaces — mem0's `user_id` / `agent_id` / `run_id` (+ optional metadata filters); Letta attaches a shared block by `block_id`.
- **Camp B (most explicit hierarchy):** Claude Code loads "broadest → most specific": **managed-policy** (org, all users) > **user** (`~/.claude/CLAUDE.md`, all projects) > **project** (`./CLAUDE.md`, shared via git) > **local** (`CLAUDE.local.md`, gitignored). Cursor: Project / User / Team rules. Windsurf: global / workspace / system.

_Confidence: high (3-0)._

### 5. Cross-agent sharing & native projection — **the load-bearing comparison for Coffer**

- **Camp A frameworks** are a **central store queried over an API/MCP**. mem0's _paper_ does not discuss cross-agent sharing; mem0's _platform_ does support `agent_id` scoping and shared instances — **but it does not project memory back into any agent's native files.**
- **The MCP memory server** is a _single shared_ JSONL graph — but "shared" means _one central file every agent reads via the same tool_, **not** "written into each agent's own native memory location."
- **Camp B product-native** systems each **read/write only their own native files** and are **mutually isolated** — Claude Code, Cursor, and Windsurf have **no cross-agent sharing layer** at all.
- **claude-mem (round-2 vote-verified).** A **central store** (SQLite + FTS5 + optional Chroma) that injects context through Claude Code **lifecycle hooks** + a worker HTTP service (`:37777`) + MCP tools. It _is_ multi-agent — but via the **same hook-plus-central-API pattern for each**, a central store agents _read from_, **not** a fan-out that writes each agent's distinct native memory file. Its only native-file write is a single auto-generated generic `CLAUDE.md` activity timeline.
- **Letta (round-3 vote-verified, 18 unanimous claims).** Letta's **shared memory blocks** let multiple agents share one block (attach by `block_id`; one update is visible to all) — **but only Letta's _own_ API-created agents**, with blocks persisted in a **central DB** (Postgres/pgvector, `BlocksAgents`/`BlockHistory` pivot tables) and _compiled into the prompt's XML at runtime_, never written to external files. Letta's docs even contrast: _"Unlike Claude Code's `CLAUDE.md` approach, Letta blocks are not written to external files."_ Its own Claude Code integration (`claude-subconscious`) **explicitly never writes `CLAUDE.md`** (stdout injection); MemFS is a single internal Letta dir; Context Repositories only _read external history one-way_ for bootstrap (the **opposite** direction to Coffer's fan-out). → Precedent for _shared memory_, **never** for native projection.
- **agentmemory (round-3 vote-verified for `jayzeng`; `rohitg00` round-2 only).** `jayzeng/agentmemory` is a **central canonical markdown store** (`~/.agent-memory/`) plus the _same_ `SKILL.md` shim installed into each agent's skills dir that calls the `agent-memory` CLI to **pull from the central store** on demand. Its `MEMORY.md` is the tool's _own_ wiki, and the README says it _"complements static files like `CLAUDE.md`, `AGENTS.md`, `.cursorrules`"_ — i.e. it **deliberately does not write into them**. Pull-from-central, the opposite of native fan-out. `rohitg00/agentmemory` (round-2 extraction, not re-verified) is a central server (MCP/REST/WebSocket) whose only native bridge is **single-target (Claude-only)**.
- **Zep/Graphiti (round-2 / background; not re-verified round 3).** A temporal knowledge graph served as a central store over an MCP/API. Central-store query model; no native-file projection.

**Verdict:** the _shared-store_ half has many precedents; the _single-target native-projection_ half has a couple (claude-mem's generic `CLAUDE.md`, `rohitg00`'s Claude bridge); the **multi-target heterogeneous native fan-out** half has **none** across three rounds. _Confidence: high (the three strongest candidates — claude-mem, Letta, `jayzeng/agentmemory` — are all vote-verified as non-fan-out; the two un-re-verified stragglers are low-risk)._

### 6. Forgetting / decay / dedup / conflict resolution

- **Camp A: active at write time** — mem0 DELETEs contradicted memories, UPDATEs, "latest truth wins"; ChatGPT auto-curates to reduce stale/contradictory entries. All **LLM-driven** (and, per issue #4896, **imperfect**).
- **Camp B: little to none, or exact-only** — MCP does exact-string dedup only; Claude Code / Cursor / Windsurf rely on **manual editing/deletion** to prevent bloat, duplication, and contradiction. Claude Code loads `CLAUDE.md` in full "regardless of length", so there is **no automatic pruning** — bloat is a human problem.

_Confidence: medium (mechanism existence 3-0; "file camp relies on manual" is a synthesis of "no auto-dedup" + "files are editable")._

### 7. Human review & correctability

- **Camp B: strong by construction** — human-readable markdown/JSONL, git-diffable, editable/deletable any time (Claude Code, Cursor, Windsurf, MCP).
- **Camp A: weak** — mem0's paper and the MCP server expose no human-in-the-loop review; memory ops are fully automatic. ChatGPT's user-visible/editable saved-memories list is the partial exception.

_Confidence: high (3-0)._

---

## Horizontal comparison

| System                | Storage / truth                                        | Write path                                                               | Retrieval                                            | Scope                            | Cross-agent + projection                                                                                                          | Dedup / conflict                           | Human review                  |
| --------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------ | ---------------------------------------------------- | -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ | ----------------------------- |
| **mem0** (base)       | Vector DB                                              | **LLM** extract + ADD/UPDATE/DELETE/NOOP (`infer=True`)                  | Vector semantic                                      | `user/agent/run_id`              | Shared store via API; **no native projection**                                                                                    | LLM at write (imperfect, #4896)            | Weak                          |
| **Zep/Graphiti**      | Temporal knowledge graph                               | LLM extract → graph                                                      | Graph traversal + vector                             | graph / namespace                | Central KG via MCP/API; **no native projection**                                                                                  | Graph reconciliation                       | Weak                          |
| **Letta** (MemGPT)    | Central DB blocks (Postgres/pgvector)                  | Agent/LLM edits blocks; compiled into prompt XML                         | Block attach by `block_id`                           | per-block / per-agent            | **Shared blocks across Letta's _own_ agents only; NO external native projection** (vote-verified)                                 | Agent-managed                              | Via API/UI                    |
| **MCP memory server** | **Single JSONL graph file**                            | Direct (agent writes), exact-string dedup                                | Substring + exact-name                               | per graph file                   | One shared central file; **not** projection                                                                                       | Exact-string only                          | Strong (editable JSONL)       |
| **claude-mem**        | Central SQLite + FTS5 (+ opt. Chroma)                  | Agent sessions distilled to store                                        | FTS5 + vector                                        | per-project                      | Central store via hooks/MCP, multi-agent; only a generic auto-`CLAUDE.md`, **no per-agent fan-out**                               | n/a                                        | Strong (SQLite/viewer)        |
| **agentmemory**       | Central md store (`jayzeng`) / server (`rohitg00`)     | Agent writes via CLI/tools                                               | CLI pull / server query                              | per-store                        | Central store; `jayzeng` = same `SKILL.md` shim pulls from central (**not** projection); `rohitg00` = single-target Claude bridge | n/a                                        | Strong (files)                |
| **Claude Code**       | **Markdown files**                                     | User-written + agent auto-notes (**no extraction**)                      | Load-in-full + on-demand (**no semantic**)           | managed > user > project > local | Native files only; **isolated**                                                                                                   | Manual                                     | Strong                        |
| **Cursor**            | `.mdc` markdown                                        | User / background-generated rules                                        | File load                                            | Project / User / Team            | Native only; isolated                                                                                                             | Manual                                     | Strong (git)                  |
| **Windsurf Cascade**  | Markdown                                               | User rules + LLM auto-memories (plain notes)                             | File load                                            | global / workspace / system      | Native only; isolated                                                                                                             | Manual                                     | Strong                        |
| **ChatGPT**           | Opaque profile + bio list                              | LLM curation + user saved                                                | Implicit profiling                                   | per-user account                 | N/A                                                                                                                               | LLM auto-curation                          | Partial (saved list editable) |
| **Coffer**            | **Markdown files-as-truth** + rebuildable SQLite index | **Direct, no LLM at write** (LLM only for batch transcript distillation) | **grep + FTS5/BM25 + sqlite-vec** (semantic, opt-in) | global + per-project (git-root)  | **One shared store → projected into N agents' native locations** (symlink where format matches, managed block elsewhere)          | **Manual / human-curated** (no auto-dedup) | **Strong** (UI + CLI + files) |

---

## Reading the field back onto Coffer

1. **Coffer's "no LLM at write time" is mainstream for file-based memory, not contrarian.** Claude Code, Cursor, and Windsurf all write memory without an extraction LLM. Coffer dropping mem0's write-time LLM puts it squarely in Camp B's company, not out on a limb.

2. **Coffer is actually _ahead_ of Camp B on retrieval.** The single biggest weakness of native-file memory is that retrieval is "load the whole file / substring match" — **Claude Code has no semantic search at all**. Coffer keeping files-as-truth _and_ adding FTS5/BM25 + sqlite-vec gives it Camp A's retrieval quality without Camp A's lossy vector-as-truth. This is a genuine best-of-both, and it is well-supported by the research.

3. **The dedup/conflict gap is real and the whole field confirms it.** Coffer inherited Camp B's weak spot: dropping mem0 dropped automatic dedup and conflict resolution, so duplicate/contradictory facts accumulate and rely on **human curation**. The research shows _everyone_ in Camp B has this same gap — but it also shows Camp A's LLM dedup is _not_ a clean win (mem0 #4896 fails on close-but-contradictory facts). So the gap is industry-wide, not a Coffer-specific defect; the open design question is whether a **lightweight optional merge/dedup pass** (mem0-style, but batch and opt-in, like Coffer already does for transcript distillation) is worth adding to get anti-bloat without sacrificing auditability. **This is now the most decision-relevant open question.**

4. **Multi-target native projection is the genuinely novel locus — now firmed (high).** Three rounds eliminated every strong candidate precedent by adversarial vote: claude-mem (central store + generic `CLAUDE.md`), Letta (shares only its own agents, central DB, prompt-XML injection), `jayzeng/agentmemory` (central store + pull-via-CLI-shim). **One canonical store fanned out into _multiple heterogeneous_ agents' own native memory locations — symlink where the format matches, managed block where it doesn't, native memory disabled to prevent divergence — was found nowhere.** That precise mechanism is Coffer's novel contribution. **But note the yellow flag:** the rest of the field _deliberately injects at runtime rather than writing native files_ — Letta's `claude-subconscious` explicitly refuses to touch `CLAUDE.md`. Coffer should be able to articulate _why_ writing/symlinking into native files (and disabling the agent's own memory) is worth the intrusiveness others avoided — the upside is ambient loading with zero per-session injection cost and true cross-agent unity, but the cost is exactly the intrusiveness `claude-subconscious` sidestepped.

---

## Caveats (carry these with the conclusions)

1. **Round-3 coverage gap.** Round 3 vote-verified **Letta** (18 unanimous) and **`jayzeng/agentmemory`** (6 unanimous), but produced **no confirmed claims for `rohitg00/agentmemory` or Zep/Graphiti** (their sources were fetched but budget-dropped before synthesis). Those two stay at round-2 primary-source / background level — low-risk (a Claude-only bridge is still single-target; Zep is a central KG service) but not vote-confirmed. Cognee, LangMem, and Llama-Index memory remain unexamined.
2. **"Paper vs platform" drift.** Several mem0 conclusions are scoped strictly to its paper (arXiv 2504.19413); the live platform/SDK has moved on (v3 multi-signal hybrid retrieval; `agent_id` scoping; OSS v2→v3 deprecated standalone Neo4j graph storage). Cite "the architecture the paper describes" vs "the current product" carefully.
3. **Absence evidence is weaker than presence evidence.** "Not mentioned" (no native projection / no cross-agent fan-out) relies on full-text search of source docs; targeted adversarial searches were run, but omissions are possible.
4. **Wording precision.** Cursor `.mdc` is _Markdown + YAML frontmatter_, not strictly "plain markdown" (the plain-markdown variant is `AGENTS.md`). ChatGPT's two mechanisms are not fully independent. mem0 write-time dedup fails on contradictory-edge cases (#4896). "agentmemory" names at least two distinct projects (`jayzeng/agentmemory`, `rohitg00/agentmemory`). DeepWiki (used to corroborate Letta's ORM) is a source-derived secondary, used as corroboration only.
5. **Recency.** Snapshot of 2025–2026 (evidence accessed 2026-06-17). Letta Code / MemFS / Context Repositories are all 2025–2026 artefacts; coding-agent memory is fast-moving — Letta's Context Repositories already read external history one-way, and a future _write-back_ would be the first system to approach Coffer's fan-out direction. Re-check within ~6 months.

## Open questions

1. _(Closed for the strongest candidates.)_ A clean re-run would convert `rohitg00/agentmemory` and Zep/Graphiti from primary-source to vote-confirmed; only worth it if the novelty claim must be defended formally. Even unverified, both are low-risk for the fan-out claim.
2. **For a file-based store, is there a mature _automatic_ anti-bloat/dedup/conflict approach, or is the field uniformly manual?** Is a thin optional LLM merge pass (mem0-style, batch) worth layering on to get both auditability and anti-bloat? **The most decision-relevant open question for Coffer.**
3. **What exactly is Coffer's projection consistency semantic** (one-way render vs two-way sync, conflict resolution, whether per-agent local edits flow back)? That is the real differentiator vs the central-store model — and the novel locus most worth hardening.
4. **Why does the rest of the field avoid writing native files (runtime injection instead)?** Letta's `claude-subconscious` deliberately never writes `CLAUDE.md`. Coffer should articulate why its native-file projection + native-memory-disabling is worth the intrusiveness others sidestepped, and watch whether the "disable the agent's own memory" sub-mechanism has any partial precedent (currently none found, but reverse-coverage is thin).

## Sources

Primary sources (vote-verified unless noted):

- mem0 — arXiv [2504.19413](https://arxiv.org/pdf/2504.19413) ([HTML](https://arxiv.org/html/2504.19413v1)); [memory operations / add](https://docs.mem0.ai/core-concepts/memory-operations/add); [issue #4896](https://github.com/mem0ai/mem0/issues/4896)
- Official MCP memory server — [modelcontextprotocol/servers/src/memory](https://github.com/modelcontextprotocol/servers/tree/main/src/memory)
- Claude Code — [memory docs](https://code.claude.com/docs/en/memory); issues [#39195](https://github.com/anthropics/claude-code/issues/39195), [#23750](https://github.com/anthropics/claude-code/issues/23750)
- Cursor — [rules docs](https://cursor.com/docs/rules); Windsurf Cascade — [memories docs](https://docs.windsurf.com/windsurf/cascade/memories)
- ChatGPT — [reference saved memories (OpenAI Help)](https://help.openai.com/en/articles/11146739-how-does-reference-saved-memories-work)
- **claude-mem** _(round 2, vote-verified)_ — [repo](https://github.com/thedotmack/claude-mem), [docs](https://docs.claude-mem.ai/introduction), [hooks architecture](https://docs.claude-mem.ai/hooks-architecture)
- **Letta** _(round 3, vote-verified, 18 unanimous)_ — [multi-agent shared memory](https://docs.letta.com/guides/agents/multi-agent-shared-memory/), [memory blocks guide](https://docs.letta.com/guides/agents/memory-blocks/), [shared-memory-blocks tutorial](https://docs.letta.com/tutorials/shared-memory-blocks/), [memory-blocks blog](https://www.letta.com/blog/memory-blocks), [context-repositories blog](https://www.letta.com/blog/context-repositories/), [`claude-subconscious`](https://github.com/letta-ai/claude-subconscious)
- **agentmemory** — `jayzeng` _(round 3, vote-verified)_: [repo](https://github.com/jayzeng/agentmemory), [SKILL.md](https://raw.githubusercontent.com/jayzeng/agentmemory/main/skills/claude-code/SKILL.md), [site](https://jayzeng.github.io/agentmemory/) · `rohitg00` _(round 2, not re-verified)_: [repo](https://github.com/rohitg00/agentmemory)
- **Zep/Graphiti** _(round 2 / background)_ — [Graphiti repo](https://github.com/getzep/graphiti), [Graphiti MCP server](https://help.getzep.com/graphiti/getting-started/mcp-server), [knowledge-graph MCP](https://www.getzep.com/product/knowledge-graph-mcp/), Zep paper arXiv [2501.13956](https://arxiv.org/abs/2501.13956)

Secondary (blogs, lower weight): agentmemory overviews ([knightli.com](https://knightli.com/en/2026/05/19/agentmemory-persistent-memory-ai-coding-agents/), [signalforges](https://signalforges.com/pages/rohitg00-agentmemory-best-practices-2026-05-13/), [dev.to](https://dev.to/andrew-ooo/agentmemory-review-persistent-memory-for-ai-coding-agents-55g2)), mem0-vs-letta-vs-zep-vs-cognee comparisons, Claude Code memory-levels explainers, mem0 [eviction/forgetting blog](https://mem0.ai/blog/memory-eviction-and-forgetting-in-ai-agents).

---

_Generated by Coffer's `deep-research` harness over three rounds. Round 1: broad landscape (25 claims). Round 2: claude-mem vote-verified. Round 3: Letta + `jayzeng/agentmemory` vote-verified (24 confirmed / 1 killed); `rohitg00/agentmemory` + Zep not re-covered. Confidence labels are the harness's, not hand-assigned._
