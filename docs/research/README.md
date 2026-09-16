# Coffer Competitive Research — Index & Synthesis

> **Fourteen** notes live in this directory — thirteen competitive-research
> reports on the product spaces Coffer touches, produced **2026-06-16/17** (and
> #13 on **2026-06-20**) via a deep-research harness (fan-out web search →
> source fetch → adversarial verification → synthesis), plus one design note
> (#14). Each report follows the same shape: product overview → capability
> comparison table → vs-Coffer → key takeaways → cited sources. (Report #12,
> memory systems, was produced by a parallel session and is listed here for a
> complete map.)
>
> **Provenance caveat (read first).** Several runs hit API rate-limiting or a
> usage-limit window during the verification/synthesis phase. Where the harness'
> own synthesis was cut short, the report was synthesized by hand from the
> harness' **primary-sourced, partially-verified claims**. Typically 2–3 claims
> per report are 3-vote confirmed; the rest are single-primary-source (cited
> inline). **Treat as a well-sourced first pass; do a light fact-check before
> quoting anything externally.**
>
> **Verification update (2026-06-19).** Every report now ends with a
> `Verification update (2026-06-19)` section — a re-verification pass that
> re-checked each report's decision-relevant claims against **current primary
> sources** (vendor docs, official repos) and **Coffer's own code / specs /
> ADRs**, recording what was ✅ confirmed, ✏️ corrected, ❓ still uncertain, or
> ➕ added (previously-uncovered competitors). Most claims held; a few
> corrections are material — e.g. the channels report's "shared approval gate"
> was removed in PR #101 (2026-06-18, two days after the report); the MCP "only
> gateway with tool-search" claim is narrowed to the tool-search-**plus**-
> agentic-`ask` combination. Read each report's update section alongside its body.
>
> _Snapshot caveat._ Coffer's skill / agent / knowledge-base subsystems are
> shipping rapidly. The per-report sections reflect `main` as re-verified on
> **2026-06-19**; two PRs that landed while this was being prepared — **#116**
> (skill discovery — browse + install from a catalog) and **#117** (co-managed
> KB documents) — are NOT folded into the per-report sections, so agent-skills'
> "no discovery" gap and parts of the KB report are already overtaken. Re-check
> against current `main` before relying on any "gap" or "we lead here" claim.

## The reports

Spec folders are **named**, not numbered. Where a report maps onto one, the
`Coffer area` column names it; where nothing in `specs/` carries the area, the
column says so.

| #   | Report | Coffer area | One-line headline |
| --- | ------ | ----------- | ----------------- |
| 1 | [MCP ecosystem](./mcp-ecosystem.md) | spec `mcp-gateway` | Coffer is the only gateway with **no per-client scoping** — every rival curates per-client. |
| 2 | [Agent config & rules mgmt](./agent-config-management.md) | spec `agent-registry` | Coffer is structurally ahead (bi-directional, safe-edit) but **doesn't distribute instructions** — the category's core feature. _Historical record — read its banner first._ |
| 3 | [Agent skills](./agent-skills.md) | spec `skill-manager` | Cross-agent delivery + SSRF-hardened ingest lead; **no skill scanner / standard-alignment** is the gap. |
| 4 | [Agent plugins](./agent-plugins.md) | spec `agent-registry` — the plugin facet (US11) | "Visibility + safe toggle, no install" is **validated**; the **plugin→hub bridge** is the novel move. |
| 5 | [Local-first control plane](./local-first-control-plane.md) | Whole-product — no single spec | "Vault for **all** assets" is unique (rivals are MCP-only); borrow **upstream sandboxing** + **profiles**. |
| 6 | [Knowledge base / RAG](./knowledge-base-rag.md) | spec `knowledge` | Files-as-truth + reindex beats locked-embedding rivals; borrow **RRF fusion + reranking**. _Historical record — read its banner first; there is no index and no `reindex`._ |
| 7 | [Messaging channels](./messaging-channels.md) | spec `channels` | Channel-as-resource + stealth pairing is distinctive (Anthropic's TG plugin is the only analog); borrow **per-conversation binding**. |
| 8 | [Multi-machine sync](./multi-machine-sync.md) | spec `vault-sync` | **Reconcile-not-overwrite** is unique; borrow chezmoi's **per-machine templating**. |
| 9 | [Credentials & secrets](./credentials-secrets.md) | **No spec folder carries this area** — credential handling lives in the constitution's Credentials constraint and in `backend/coffer/infrastructure/credentials/` | Coffer already implements 1Password's "**access without exposure**" ideal; borrow **external-provider refs** (`op://`). |
| 10 | [Observability, audit & MCP security](./observability-governance.md) | Cross-cutting (audit / retention / security) — no spec folder of its own | Governance/audit is **ahead** (free vs Langfuse's paywall); borrow **MCP tool-pinning** (mcp-scan). |
| 11 | [Agent evaluation](./agent-evaluation.md) | Eval flywheel / harness — no spec folder of its own | **Correction: the flywheel shipped** (the eval-flywheel ADR is accepted, `evals/` exists); borrow **LLM-as-judge**. |
| 12 | [Memory systems](./memory-systems-landscape.md) | spec `memory` | _Parallel session._ Field splits file-truth vs vector-truth; Coffer was a deliberate hybrid until the index came out — the note's dated updates fold that reversal in. |
| 13 | [Platform-level competitors](./platform-competitors.md) | Whole-product (re-sweep) — no single spec | **Blind-spot fix (2026-06-20):** the prior 12 reports missed cc-switch (~105k) + the whole Chinese ecosystem; no incumbent covers Coffer's full 10-capability matrix. |
| 14 | [Machine × agent resource scope](./machine-agent-scope.md) | spec `vault-sync` + the resource framework's scope facility | _Design note (2026-07-10), not a competitive report._ **Historical record** — it designed a machine × agent scope matrix; a resource's reach is now machine-local and `scope` names agents and nothing else. |

Two named specs have no report here: `provider-switching` and `ui-shell`.

## Cross-cutting themes (as of 2026-06-20)

> **Dated snapshot, not live guidance.** The synthesis below reads across the
> thirteen reports as they stood on **2026-06-20**. Several of its
> recommendations have since shipped and several of its claims about Coffer are
> no longer true; each is corrected inline with a dated note. Treat the
> section as a record of what the research concluded, and check
> `.specify/memory/architecture.md` before acting on any line of it.

Reading across all thirteen reports, a few patterns recur:

### Coffer's recurring differentiators (lead with these)

- **Breadth: one vault for _all_ agent assets.** No competitor goes beyond MCP
  (control-plane). Everything-is-a-resource + files-as-truth is a durability
  story none of them tell.
  **Correction (2026-09-14):** this bullet originally read "files-as-truth +
  rebuildable index". There is no index. The knowledge layer's tables were
  dropped on 2026-09-12
  ([Knowledge Is Plain Files](../decisions/knowledge-is-plain-files.md)) and
  every embedding engine was removed on 2026-09-14 — Coffer embeds nothing,
  and retrieval is literal.
  Files-as-truth survives, and is in fact more literally true than when the
  bullet was written; the rebuildable-index half of the durability story does
  not.
- **Bi-directional ingest→hub→deliver.** Every config/skill rival is
  one-directional generation; only Coffer also _adopts_ (config, plugins, skills).
- **Privacy-scoped by construction.** No-payloads invocation log, ciphertext-only
  credentials ("access without exposure"), single-owner stealth channels, free
  mandatory audit (vs Langfuse paywalling it). Aligned with the industry's own
  stated ideals, by default.

### The single most-validated gap: per-client / per-agent scoping — **closed**

Two independent reports (MCP ecosystem, control-plane) flagged the same thing:
Coffer injected the **whole gateway into every agent**, while ContextForge
(virtual servers), MetaMCP (namespaces), MCPJungle (tool groups), Docker
(profiles), and mcpm (profiles) all exposed **per-client subsets**. It was both
a UX fix (it's _why_ `search_tools` exists, papering over self-inflicted overload)
and a security fix (withhold a sensitive server from an agent), and the research
called it the highest-priority borrow.

**Update: this shipped.** Per-agent scope is now a framework-level facility
([Per-Agent Resource Scope](../decisions/per-agent-resource-scope.md)) — see
`backend/coffer/domain/scope.py` and the gateway's own enforcement point,
`backend/coffer/application/mcp/gateway_scope.py`. **Six of the seven resource
kinds declare `supports_scope=True`** (`mcp`, `skill`, `channel`, `knowledge`,
`memory`, `provider`); the one that does not is **`agent`**, deliberately — scope
names the agents a resource is active for, so an agent scoping itself is
meaningless, and a non-null scope on an agent is rejected at validation. A
resource's reach is **machine-local**: it is set on the machine it applies to
and never synced.

### A cross-cutting security/integrity opportunity

Supply-chain / integrity threats recur in three reports — skills (ToxicSkills,
OWASP Agentic Skills Top 10, scanner-evasion), plugins (GlassWorm, Open VSX),
and MCP (tool-poisoning, rug-pull; mcp-scan's **Tool Pinning**; the space is
consolidating into Snyk/SentinelOne). Coffer's SSRF-hardened ingest is a head
start, but it does **not scan content or pin tool definitions.** A "trust/
integrity layer" (skill scanning + MCP tool-definition pinning + provenance)
is a single initiative that pays off across skills, plugins, and MCP — and is
squarely on-mission for a "vault."

### Conform to the open standards

Each space has a standard Coffer should consume/conform to for portability:
**agentskills.io** (skills), **AGENTS.md** (instructions), the **official MCP
Registry** (MCP discovery), and **OpenTelemetry GenAI** (if/when model tracing —
note it's still pre-GA).

### Other recurring borrows

- **RRF hybrid fusion + reranking** for the KB (every serious RAG peer does it).
- **External-provider credential refs** (`op://`) so users don't duplicate
  secrets into Coffer; plus **per-machine templating** for sync (chezmoi).
- **Instructions/rules as a hub-delivered asset** — the one "missing kind"
  (Coffer does MCP + skills hub delivery, not instructions).
- **Breadth:** light up the 4 wired-but-hidden agents (rivals cover 12–28).
  **Correction (2026-09-14):** superseded, and in the opposite direction. There
  are no hidden agents to light up: `AgentType` is now exactly `claude_code` and
  `codex`, and the manifest defines exactly two `AgentDescriptor` records. The
  four the borrow refers to (Cursor / OpenCode / OpenClaw / Hermes) were
  **removed**, not enabled. Breadth against rivals' 12–31 agents is a gap Coffer
  has chosen to keep.

### Two factual corrections the research surfaced

- **KB** exposes granular MCP tools rather than a single question-answering
  entry point. The count in this bullet was **four read-only** tools
  (list / search / grep / read). **Correction (2026-09-14):** knowledge now
  contributes **six** tools, and two of them **write**: `list`, `grep`, `read`,
  `search`, `write`, `delete`. The read-only posture the research praised is
  gone — an agent can create and delete knowledge files through the gateway.
- **Eval is not a blueprint** — the eval-flywheel ADR is Accepted (2026-06-14) and a working
  local-first `evals/` harness has shipped (capture → curate → golden → CI-gate).

## Coverage note

One flagged coverage gap from the KB run — AnythingLLM, Onyx, Khoj, Morphik,
LlamaIndex were under-evidenced — has a **targeted follow-up** whose results are
folded back into [knowledge-base-rag.md](./knowledge-base-rag.md).

A larger, structural coverage gap — the per-area shape of reports 1–12 missed
**platform-level competitors** (tools spanning many categories at once) and the
**Chinese desktop-switcher / relay / IM ecosystem** entirely, including the
market leader **cc-switch (~105k)** — is addressed by report #13,
[platform-competitors.md](./platform-competitors.md) (a stars-first +
capability-matrix re-sweep, 2026-06-20). Re-run competitive scans stars-first
across the keyword space and include the Chinese ecosystem by default.

## Method

Each report = one deep-research run: the question decomposed into ~5 search
angles → parallel web search → top sources fetched → falsifiable claims extracted
→ 3-vote adversarial verification → synthesis. Runs that read Coffer's own
repo/specs to verify the comparison are noted in those reports (KB, eval).
