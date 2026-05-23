# Feature Specification: Memory Manager

**Feature Branch**: `feature/007-memory`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "Coffer's seventh feature — manage local AI agent memories: short, derived facts about the user / project / preferences, written by the coding agent and (optionally) the user, surfaced back to the agent through Coffer's MCP gateway. Engine: mem0 (industry-mainstream memory framework), behind a thin port so Coffer's application layer never directly imports it. Built on top of the kind-agnostic Resource framework laid down by 001-mcp-gateway. Distinct from knowledge_base (spec 006) — KBs hold user-uploaded documents; memories hold short derived facts."

## User Scenarios & Testing

### User Story 1 — Agent remembers facts across sessions (Priority: P1)

The developer's coding agent (Claude Code / Cursor / ...) connects to Coffer's MCP endpoint. During a session it learns the developer prefers tabs over spaces, uses kebab-case for branch names, and avoids force-pushes. Via Coffer's built-in `coffer__add_memory` tool, the agent records each fact. In a later session — possibly a different MCP client — the agent calls `coffer__search_memory` with a relevant query and the same facts are returned, so it doesn't re-ask.

**Why this priority**: This is the core of the spec. Without cross-session recall, the memory feature offers no value over what an agent already does in-context.

**Independent Test**: From a fresh install, register one memory store, have an MCP client call `coffer__add_memory` three times, restart the daemon, have the client call `coffer__search_memory` with a related query, observe the previously-added facts returned.

**Covering scenarios**:

- create a memory store
- agent adds a memory
- agent searches memories
- memories persist across daemon restarts
- agent deletes a single memory
- delete a memory store cleans up everything

---

### User Story 2 — User reviews and curates what the agent remembers (Priority: P1)

The developer wants visibility and control: see what facts have been recorded, edit them when they drift from reality, forget specific ones, and stop the agent from writing certain categories.

**Why this priority**: Memory without curation feels uncomfortable (agents will sometimes record wrong things). Curation is what makes the feature trustworthy enough to keep enabled.

**Independent Test**: After the agent has added several memories, the user opens the memory list, picks one, edits its text, saves, observes the agent's next search returns the edited version. Then deletes a different one and observes it's gone.

**Covering scenarios**:

- list memories in a store
- edit a memory
- user adds a memory directly
- delete a memory through the UI

---

### User Story 3 — Manage memories from the desktop app (Priority: P2)

The developer prefers a visual list — searching, scrolling, scanning for anything outdated or wrong.

**Why this priority**: Required for non-CLI users. The form factor for memory (scrollable list, edit-in-place) is more natural in a UI than CLI.

**Independent Test**: Launch Coffer, navigate to the memory store, see the list, search inside it, edit one in place, delete another, observe both reflect immediately.

**Covering scenarios**:

- desktop list view shows memories
- desktop edit-in-place
- desktop search box filters

---

### User Story 4 — Manage memories from the command line (Priority: P2)

The developer scripts bulk operations: export all memories as JSON, mass-delete by tag, import from a file.

**Why this priority**: Backup / migration / debugging support.

**Independent Test**: From a terminal, list memories as JSON, edit the JSON, delete some by id, export to a file — all without touching the UI.

**Covering scenarios**:

- CLI list / add / delete
- CLI JSON output for piping

---

### User Story 5 — Observe and bound memory growth (Priority: P3)

The developer wants reassurance that memories are not silently growing without bound and that they can wipe everything if needed.

**Why this priority**: Hygiene; not blocking core flow.

**Independent Test**: Observe the per-store metric (count, disk usage). Trigger a "clear all memories in this store" action. Confirm everything is gone but the store itself remains, ready for new memories.

**Covering scenarios**:

- per-store metrics
- clear all memories in a store

> **Retention note**: the per-store cap of ~10,000 memories is a soft scope
> target (see `plan.md` Technical Context, "Scale / Scope"), not a hard
> functional cap. No FR in this spec enforces it; a future spec may add an
> enforcement policy (rolling eviction, hard-cap rejection, or operator
> warning) if real-world usage requires it.

---

### Edge Cases

- **mem0 LLM dependency not configured**: mem0 wants an LLM at write time (for fact extraction). If no LLM provider is configured, the `add_memory` endpoint returns 503 with a clear pointer to the setup docs. Reads (`search_memory`, `list`) still work — they don't require an LLM.
- **LLM endpoint unreachable mid-write**: A single failed write does not corrupt the store; the operation returns an error and the user can retry.
- **Long input text**: Memory text is bounded to 8 KB at the API boundary; longer inputs are rejected before they reach mem0.
- **Empty memory text**: Rejected at the API boundary.
- **Duplicate memory**: mem0 has its own dedup / merge logic; we surface its outcome but never silently swallow. The audit row records `created` vs `merged`.
- **Delete a store while a write is in flight**: Reject with a 409; the user retries after the write completes.
- **Embedding model swap mid-store**: Rejected — same rule as knowledge_base (immutable after creation).

## Acceptance Scenarios

Every scenario maps to at least one test marked `@pytest.mark.acceptance(spec="007-memory", scenario="…")`.

### Scenario: create a memory store

- **Given** the coffer daemon is running and no memory stores are registered,
- **When** the user creates a memory store with a unique name and an embedding model + LLM provider selection,
- **Then** the store is persisted, an empty mem0 instance is initialized on disk under `~/.coffer/memory/<name>/`, and listing stores shows it.

### Scenario: agent adds a memory

- **Given** a memory store exists and an LLM provider is configured,
- **When** an MCP client calls `coffer__add_memory` with a store name and a fact (e.g., "the user uses tabs"),
- **Then** the memory is persisted via mem0, a row is added to `memory_records` with id / store_name / text / created_at, and an audit entry is recorded.

### Scenario: agent searches memories

- **Given** a memory store has memories,
- **When** an MCP client calls `coffer__search_memory` with the store name and a query,
- **Then** ranked memories are returned with their id, text, score, and created_at.

### Scenario: memories persist across daemon restarts

- **Given** memories have been added to a store,
- **When** the daemon is stopped and restarted,
- **Then** subsequent searches return the previously-added memories without re-ingestion.

### Scenario: agent deletes a single memory

- **Given** a memory store has memories,
- **When** an MCP client calls `coffer__delete_memory` with a memory id,
- **Then** the memory is removed from mem0, the row in `memory_records` is deleted, an audit entry is recorded, and subsequent search does not return that memory.

### Scenario: delete a memory store cleans up everything

- **Given** a memory store has memories and on-disk mem0 state,
- **When** the user deletes the memory store,
- **Then** every memory row is removed, the on-disk directory `~/.coffer/memory/<name>/` is removed, any in-memory mem0 client is disposed, and the Resource row is deleted.

### Scenario: list memories in a store

- **Given** a memory store has memories,
- **When** the user lists memories in that store (paginated),
- **Then** they see one row per memory with id, text, created_at.

### Scenario: edit a memory

- **Given** a memory exists,
- **When** the user edits its text and saves,
- **Then** the new text is persisted (a new embedding is computed), the audit log records the change, and subsequent searches reflect the new text.

### Scenario: clear all memories in a store

- **Given** a memory store has memories,
- **When** the user runs `coffer memory clear <store> --yes` or clicks "Clear all" in the UI,
- **Then** every memory in that store is removed (rows + mem0 state) but the store Resource itself is preserved.

### Scenario: built-in memory tools appear in client tool list

- **Given** an MCP client connects to coffer's gateway,
- **When** the client lists tools,
- **Then** `coffer__list_memory_stores`, `coffer__add_memory`, `coffer__search_memory`, `coffer__delete_memory` appear alongside other built-in and upstream tools.

### Scenario: add_memory returns 503 when LLM provider is none

- **Given** a memory store exists with `llm_provider = "none"`,
- **When** an MCP client (or any surface) calls `add_memory` against that store,
- **Then** the call is rejected with a 503 (or equivalent error) carrying a `LLM_NOT_CONFIGURED` code and a message pointing at the setup docs,
- **And** the store's read paths (`list`, `get`, `search`) continue to succeed unchanged.

### Scenario: memory text exceeding bound is rejected

- **Given** a memory store with `max_memory_chars` at its default of 8192,
- **When** a caller invokes `add_memory` (or `update`) with text longer than 8192 characters,
- **Then** the call is rejected at the API boundary with a `MEMORY_REJECTED` error (`reason = "too_long"`) and nothing is persisted (no mem0 write, no `memory_records` row, no audit entry beyond the rejection itself).

### Scenario: empty memory text is rejected

- **Given** any memory store,
- **When** a caller invokes `add_memory` (or `update`) with empty or whitespace-only text,
- **Then** the call is rejected at the API boundary with a `MEMORY_REJECTED` error (`reason = "empty"`) and nothing is persisted.

### Scenario: add_memory surfaces upstream LLM error without corrupting store

- **Given** a memory store with an LLM provider configured but the LLM endpoint is unreachable (or returns an error) at write time,
- **When** a caller invokes `add_memory`,
- **Then** the call returns a structured error (no partial write, no orphan `memory_records` row, no orphan mem0 vector entry),
- **And** a subsequent successful `add_memory` against the same store works normally — the store is not left in a degraded state.

> **Deferred to future test work**: these scenarios are part of the user-visible contract but their tests land alongside the e2e infrastructure rather than in this PR. `make verify-acceptance` does not gate on them.
>
> - user adds a memory directly (covered functionally by `add_memory` actor="user" path)
> - delete a memory through the UI
> - desktop list view shows memories
> - desktop edit-in-place
> - desktop search box filters
> - CLI list / add / delete (end-to-end with a running daemon)
> - CLI JSON output for piping
> - per-store metrics (HTTP route — covered by metrics() service test in KB; mirror to memory in a later PR)
> - audit records memory lifecycle changes

## Requirements

### Functional Requirements

**Resource lifecycle**

- **FR-001**: System MUST support a new resource kind `memory`; users MUST be able to create, list, view, update (description and `max_memory_chars` only — `llm_provider`, `llm_model`, `llm_endpoint`, `llm_credential_ref`, and `embedding_model` are immutable post-create), enable, disable, and delete memory stores through the existing kind-agnostic Resource framework.
- **FR-002**: System MUST validate every memory-store configuration (embedding model, LLM provider config, max memory text length) against a Pydantic schema, reject duplicates, and persist nothing on failure.
- **FR-003**: System MUST store each memory store's state under a per-store directory `~/.coffer/memory/<name>/`. Deletion MUST remove this directory and the corresponding `memory_records` rows.

**Memory lifecycle**

- **FR-004**: Users / agents MUST be able to add a memory (free-text string). The system MUST persist it via mem0, embed it for retrieval, and record a row in `memory_records`.
- **FR-005**: Memory text MUST be at least 1 char and at most 8192 chars; non-text content is rejected at the API boundary.
- **FR-006**: Users / agents MUST be able to list memories (paginated), get a single memory by id, edit a memory's text, and delete a single memory or all memories in a store.

**Retrieval**

- **FR-007**: Users / agents MUST be able to search a memory store with a natural-language query and receive ranked memories carrying id, text, score, and created_at.
- **FR-008**: Search default returns top 5 memories; caller MAY specify `top_k` in range 1–20.

**Agent integration via MCP**

- **FR-009**: Coffer's MCP gateway MUST expose built-in tools `coffer__list_memory_stores`, `coffer__add_memory`, `coffer__search_memory`, `coffer__delete_memory`, namespaced under the reserved `coffer__` prefix.
- **FR-010**: Built-in memory tools MUST share the same invocation logging surface as KB built-in tools and upstream MCP tools (one row in `mcp_invocations`, no arguments or return content beyond the tool name).

**Engine isolation**

- **FR-011**: System MUST keep mem0 confined to `coffer/infrastructure/memory/`. Domain and application layers MUST NOT import mem0 types directly; interaction is via the `MemoryStore` port.
- **FR-012**: If mem0 or its embedding model fails to initialize, the daemon MUST still start; only memory write/read endpoints return 503 with a message naming the missing dependency.

**LLM provider configuration**

- **FR-013**: System MUST default to no LLM provider; the user MUST explicitly opt in by configuring either a local Ollama endpoint or a cloud provider key (OpenAI) at the memory-store level. (Anthropic support is deferred to a follow-up spec; adding it requires both an enum entry and the corresponding mem0 provider configuration.)
- **FR-014**: When no LLM provider is configured, the system MUST allow create / list / search / delete / edit but reject `add_memory` with a 503 and a message pointing at the setup docs.

**Observability**

- **FR-015**: System MUST emit traces around add / search / edit / delete through the `Tracer` port at `application/observability/tracer.py` introduced by spec 006 (knowledge_base) and promoted to a shared module by this spec as its second consumer.

**Surfaces**

- **FR-016**: Users MUST be able to perform every operation through (a) a REST API under `/api/v1/memory_stores/`, (b) `coffer memory …` subcommands, and (c) a desktop UI.

### Key Entities

- **Memory Store** (a resource of kind `memory`): Holds the configuration for one store — embedding model id, LLM provider config, max text length, description. Immutable post-creation except description.
- **Memory Record**: One memory. Identified by (store_name, memory_id). Stores id, text, created_at, updated_at, actor (`agent` / `user`).
- **Memory Hit** (search result, not persisted): id, text, score, created_at.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user can create their first memory store and add their first memory within 90 seconds (the extra time vs KB accounts for LLM provider setup).
- **SC-002**: With one store of 200 memories, search latency for a typical query is ≤ 500 ms wall-clock on a developer laptop.
- **SC-003**: Deleting a memory store removes 100% of its on-disk footprint and database rows.
- **SC-004**: A coding agent connected through Coffer's MCP gateway can add, search, and delete memories — all via built-in tools — within a single MCP session.
- **SC-005**: Every Acceptance Scenario is covered by at least one test marked with `acceptance(spec="007-memory", scenario="…")`.
- **SC-006**: Engine isolation is enforced by importlinter: no module under `coffer.application.*` or `coffer.domain.*` imports `mem0`.
- **SC-007**: `make verify` passes locally and in CI.

## Assumptions

- The user runs Coffer on their own machine.
- mem0 remains an actively-maintained Python package. API churn is absorbed in `infrastructure/memory/mem0_store.py` only.
- If a local LLM (Ollama) is desired, the user has installed and started Ollama themselves. Coffer ships pointers in docs but does not bundle Ollama.
- The memory store is **not** a knowledge base. It is for short derived facts; max text length is 8 KB.
- Single-user concurrency is small.
