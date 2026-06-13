# ADR-020 — Transcript Distillation: Read Agent Transcripts, Write Memory Facts

> 中文版: [ADR-020-transcript-distillation.zh.md](./ADR-020-transcript-distillation.zh.md)

- **Status:** Accepted
- **Spec:** [007-memory](../../specs/007-memory/spec.md) (extension — no new spec number)
- **Related:** [ADR-012](./ADR-012-files-as-truth-sqlite-retrieval.md) (files-as-truth + SQLite retrieval), [ADR-013](./ADR-013-agent-native-shared-memory.md) (agent-native shared memory), [ADR-016](./ADR-016-multi-machine-sync.md) (multi-machine sync), Spec 004 (agent registry — read-only workspace invariant)

## Context

Coffer agents interact with coding agents (Claude Code, Codex) in real time
through the MCP `recall`/`remember` gateway. But those sessions also produce
local chat transcripts — `.jsonl` files written to `~/.claude/projects/` or
`~/.codex/sessions/` — that may contain durable engineering decisions,
project conventions, failed approaches, and open todos that were never
explicitly recorded as memory facts. This institutional knowledge would be
lost between sessions and invisible to other agents and machines.

We want to surface that knowledge without:
- persisting raw transcript content (which contains secrets, tool payloads,
  file contents, and command output),
- writing into the foreign agent's own session store (which Coffer must not
  own or corrupt), or
- requiring a new top-level spec (the output is memory facts, governed
  entirely by existing Spec 007 invariants).

## Decision

Add a **transcript distillation** capability as an extension of Spec 007
Memory. It operates in three read-only-ingest steps:

1. **Read** — A `TranscriptReaderPort` adapter reads `.jsonl` files from the
   registered agent's workspace config dir (e.g. `~/.claude/projects/` for
   Claude Code, `~/.codex/sessions/` for Codex). This mirrors Spec 004's
   allowlist-based config-file reading: files are read, never written.

2. **Scrub and distill** — Natural-language turns (user + assistant text) are
   extracted; all `tool_use` / `tool_result` blocks, file-content passages,
   and command output are dropped. A one-shot LLM call (via the existing
   `build_chat_model` infrastructure) receives the scrubbed conversation and
   returns a JSON array of structured insights typed as `decision`, `gotcha`,
   `convention`, or `todo`.

3. **Write facts** — Each distilled insight is written through
   `InsightSinkPort` → `MemoryService` as a project-scoped memory fact
   (Spec 007 `MemoryFact` with `actor="agent"`, `origin_session_id` set to
   the transcript session id). No raw transcript content reaches the fact
   body.

Cross-agent sharing and cross-machine sync are automatic consequences: memory
facts are already shared over the MCP `recall` gateway (Spec 007) and synced
over git (Spec 010 / ADR-016). No new infrastructure is needed.

### Architecture — a self-contained `distill` slice

A new `distill` slice sits across all four layers
(`domain/distill/`, `application/distill/`, `infrastructure/distill/`,
`surfaces/http/distill/`) and communicates with `agent` and `memory` slices
**only through ports wired at the composition root** (`surfaces/http/wiring.py`).
This is the only site that imports across kind boundaries (satisfying
import-linter Contract 5). Application-layer code in `application/distill/`
must not import `application.agent`, `application.memory`, or any
`infrastructure.*` module.

### Invariants

- **No raw transcript persistence.** `tool_use`/`tool_result` blocks, file
  contents, and command output are dropped during parse. Only scrubbed
  natural-language text is passed to the LLM. Only distilled facts are
  stored.
- **Never write into the foreign agent's session store.** Coffer reads
  `~/.claude/` and `~/.codex/` but never writes to them in this flow. Spec
  004's read-only invariant is fully preserved.
- **Provenance on every fact.** Each distilled fact carries
  `origin_session_id` (the transcript's session id) and `actor="agent"` so
  its automated origin is auditable.
- **Secret scrubbing before LLM.** Message text is run through a regex
  scrubber that redacts common secret patterns (API keys, tokens, private
  key blocks) and truncates long blobs before they reach the LLM.
- **Defensive parsing.** The `.jsonl` formats of Claude Code and Codex are
  undocumented and unstable. Per-agent read adapters (`parse_claude_code`,
  `parse_codex`) skip unknown lines and never raise on a single bad record.
  The ecosystem research finding: no major agent persists or syncs raw
  transcripts over a shared medium; the cross-agent sharing pattern is
  distilled memory.

## Alternatives considered

### A — New hub resource kind: `conversation` / `transcript`

Store full (or scrubbed) transcripts as a new Coffer resource kind, sync
them via Spec 010 git, and let agents query the transcript corpus directly.

**Rejected.** Raw transcripts are large and contain secrets, tool payloads,
and file contents. ADR-012's files-as-truth model and the roadmap's explicit
non-goal ("tool call argument or result persistence") both prohibit persisting
tool-call content. Syncing multi-megabyte JSONL over the user's git repo
(ADR-016) would bloat history and pollute diffs. Nobody in the agent
ecosystem syncs raw transcripts over a user-controlled git repo; the dominant
cross-agent sharing pattern is sharing distilled memory. Introducing a new
kind would also require UI, API, migration, and contract work that yields no
additional user value over distilled facts that are already surfaced by
`recall`.

### B — Local transcript browser in the Agent Chat page (Spec 008)

Add a tab to the existing Spec 008 Agent Chat page that lists past sessions
and lets the user browse or "continue" a conversation by re-injecting
transcript turns into a new session.

**Rejected** for v1. The durable value to the user is the distilled knowledge
persisting into memory, not replay of a past exchange. A browser/continue
feature is additive work on a different problem (session resumption) and has
no traction in the ecosystem. It does not affect this ADR and can be added
independently if there is user demand.

### C — Write back into the foreign agent's session store

Persist distilled insights as new entries directly into `~/.claude/` or
`~/.codex/` so the coding agent natively "sees" the distilled facts in its
own history.

**Rejected.** This would violate Spec 004's read-only invariant: "internal
state files are read, never written." It also requires reverse-engineering
each agent's write format (which is undocumented and can change), and writing
malformed entries could corrupt the user's real agent history. The correct
injection channel is the MCP `recall` gateway (already in place) and native
projection (Spec 007 FR-012/FR-013) — not direct writes into the agent's
own session store.

## Consequences

- A new `distill` slice is added across all four layers; it depends only on
  its own Protocol ports (wired in `wiring.py`), keeping import contracts
  clean.
- Two new HTTP routes: `GET /api/v1/agents/{name}/transcripts` (list
  sessions) and `POST /api/v1/agents/{name}/transcripts/distill` (run
  distillation). Contract declared in
  `specs/007-memory/contracts/transcripts.openapi.yaml`.
- A `coffer transcript list|distill` CLI subcommand provides scriptable
  access.
- The frontend adds an "Conversations" tab to the Agent detail page (distill
  a session to memory with one click).
- No new spec number. Spec 007 User Stories, acceptance scenarios, and
  functional requirements are extended in place.
- The transcript `.jsonl` format is undocumented; the per-agent adapters are
  marked defensive and must be updated when agent vendors publish stable
  formats or change the schema in a breaking way.
