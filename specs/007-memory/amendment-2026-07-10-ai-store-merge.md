# Amendment 2026-07-10 — AI-assisted merge of same-project memory stores

> 中文版: [amendment-2026-07-10-ai-store-merge.zh.md](./amendment-2026-07-10-ai-store-merge.zh.md)

Status: **accepted** (implemented with this amendment's PR)
Amends: [spec 007 — Memory](./spec.md) · no new spec number (like the transcript-distillation extension)
Adds: **FR-056 – FR-059** to `spec.md`, four acceptance scenarios, two REST endpoints, two CLI subcommands, one store-list UI action.
Scope axis unchanged: lanes, files-as-truth (ADR-012/013), and the portable project identity (FR-004a) stay exactly as they are. This amendment only adds a **user-triggered, engine-judged consolidation path** for stores the deterministic consolidator cannot prove equal.

## Motivation

Multi-machine sync (spec 010) and the pre-portable-identity era can leave the
store list with several `project-<ULID>` stores that are really **one**
project:

1. A checkout with **no `origin` remote** hashes to a path-derived id — a
   different id per machine (and per path) for the same repo.
2. A store minted **before portable identity** (FR-004a) on another machine
   arrives via sync under its legacy id; the local machine holds the same
   project under the portable id. Resolve-time adoption only heals the pair
   when the legacy store's root is locally resolvable — a synced-in store's
   root usually is not.
3. A repo whose **remote URL changed** (fork rename, host migration) mints a
   second identity.

The deterministic consolidator (boot pass + resolve-time adoption) collapses
only stores whose roots **re-resolve to the same canonical id** — it cannot
know that two *different* identities mean the same project. Judging "same
project?" from labels, paths, and content is a judgment call — exactly what
Coffer's internal engine (the FR-033 pattern) is for. The user then confirms,
and the existing additive merge machinery consolidates the facts.

## Out of scope

- **No automatic or background merging** — scan and merge are explicit user
  actions (`POST` endpoints / CLI / UI button), like the FR-033 reorg pass.
- **No persistence of rejected proposals** — a dismissed pair is simply
  re-proposed by the next scan (YAGNI until it hurts).
- **No cross-machine orchestration** — a merge runs on one machine; the
  outcome travels through the normal sync areas (resource tombstone for the
  retired store, lane files and config for the survivor).
- **No merging the global store** — project stores only.
- **No new DB schema** — identity aliases ride the surviving store's
  `config_json` (`MemoryStoreConfig.merged_identities`), so no migration.

## Change A — merge scan (FR-056)

`POST /api/v1/memory_stores/merge_scan` (and `coffer memory merge-scan`)
examines every pair of per-project stores and returns **merge proposals**.

- **Evidence per store** (gathered server-side, never sent anywhere but the
  configured internal engine): store name, display label (FR-017c), recorded
  `project_root`, the root's **normalized origin remote** when the root is
  locally readable (`normalize_remote_url`, FR-004a), fact count, and a
  bounded sample of fact titles + topic slugs.
- **Deterministic tier first**: two stores whose locally-readable roots
  normalize to the **same non-empty remote URL** are proposed with
  `confidence="certain"` and `judged_by="remote"` — no LLM involved.
- **Engine tier**: remaining pairs go to the internal engine (FR-033's
  internal-default connection) one **one-shot completion per pair** — strict
  JSON verdict `{same_project, confidence, reason}`; a malformed response
  skips the pair (organizer skip semantics — never a crash, never a guess).
- **Degrades cleanly**: with no internal engine configured the response is
  `engine="no_model"` and carries the deterministic-tier proposals only.
- **Bounded**: the engine tier judges at most 50 pairs per scan (response
  flags `truncated=true` when the cap bites); evidence samples are capped so
  a large store cannot blow the context window.
- **Suggested direction**: each proposal names a suggested `target` (the
  surviving store) — the store with a locally-resolvable root wins, then the
  higher fact count, then the lexically smaller name (deterministic).

## Change B — merge execution (FR-057)

`POST /api/v1/memory_stores/merge` with `{source, target}` (and
`coffer memory merge <source> <target>`) consolidates two project stores
using the **existing additive merge machinery** (`merge_store_dir` — the
boot-consolidation/adoption primitives):

- Journal files content-merge entry-by-entry deduped by timestamp; derived
  files are skipped; any other collision keeps **both** copies (suffixed) —
  memory can be gained, never lost.
- The source's display label moves to the target when the target has none;
  the source's `project_root` mapping moves likewise.
- The target is reconciled (force) so recall reflects the merged facts, the
  source store is retired (resource delete cascades docs/index/dir), and one
  `memory_stores_merged` audit entry is recorded (store names + counts only).
- Validation: `source` and `target` must be **distinct, existing, per-project
  stores** — the global store is never mergeable; violations are 4xx with no
  side effects.
- Merges serialize with resolve-time adoption (same lock). Fact writes do
  NOT hold that lock, so the merge **re-sweeps the source immediately before
  retiring it** (the file merge is content-idempotent, so the sweep only
  picks up genuinely new files) — anything remembered mid-merge is carried
  over; a write after retirement fails loudly instead of landing in a
  doomed directory.

## Change C — no-resurrection identity aliases (FR-058)

Merging `project-X` into `project-Y` must also make **future resolves** of
identity `X` land on `Y` — otherwise the next `remember` from the checkout
that minted `X` silently re-provisions an empty duplicate and the pair is
back on the next scan.

- The surviving store's config gains **`merged_identities`** (a list of
  project ULIDs, system-managed, default empty). A merge appends the source's
  ULID **and** the source's own `merged_identities` (transitive, so chained
  merges keep every alias).
- `ScopeResolver._resolve_project` consults the aliases **only on a miss**:
  when the computed identity's store does not exist, a store whose
  `merged_identities` contains the identity resolves instead (the hot path —
  store exists — is untouched).
- Because the alias lives in the resource's `config_json`, it **syncs** with
  the resource (spec 010): the redirect holds on every machine, and the
  retired store's deletion propagates as a normal resource tombstone.
- **Exactly one live holder per identity**: recording aliases on a new
  holder strips them from every other store's `merged_identities`, so the
  redirect is never ambiguous.
- **The boot consolidation pass honors the aliases too**: a canonical
  identity that was merged away redirects to its alias holder instead of
  being re-provisioned — without this, a survivor whose recorded root
  re-resolves to a merged-away identity would be "healed" back into an
  empty duplicate at the next startup, reversing the merge. Boot/adoption
  merges also carry the retired store's aliases (and record the retired
  identity itself) on the canonical store.

## Change D — post-merge organize (FR-059)

"Merge the facts" is more than moving files: overlapping topic documents from
the two stores should be consolidated. The merge endpoint accepts
`organize` (default `true`): after a successful merge, when the internal
engine is configured, the existing **FR-033 reorg pass** runs on the target
store and its outcome is reported as `reorg_status` in the merge response
(`"reorganized"`, `"no_model"`, `"empty"`, `"skipped"` when `organize=false`,
or `"error: …"`). The merge itself never fails because the organize step
failed — files-first, polish-second.

## Contract / API delta

- `POST /api/v1/memory_stores/merge_scan` → `202`-style synchronous JSON:
  `{engine, truncated, proposals: [{source, target, confidence, judged_by,
  reason, source_evidence, target_evidence}]}`.
- `POST /api/v1/memory_stores/merge` body `{source, target, organize?}` →
  `{target, merged_files, label_moved, root_moved, aliases, reorg_status}`.
- `MemoryStoreConfig` gains `merged_identities: string[]` (default `[]`).
- Update `contracts/api.openapi.yaml` + the contract test.

## Frontend

- The memory-store list gains a **"Find duplicates (AI)"** toolbar action →
  runs the scan, shows proposals (pair, confidence, judged-by, reason) in a
  dialog with per-proposal **swap direction** and **Merge** buttons; a merge
  invalidates the store-list query. `engine="no_model"` renders the
  deterministic proposals plus a hint to configure the internal engine.

## CLI

- `coffer memory merge-scan [--json]` — print proposals.
- `coffer memory merge <source> <target> [--no-organize] [--json]` — execute.

## Test plan

Unit: verdict prompt build/parse (fence-strip, malformed → skip), candidate
pairing + deterministic tier, target-direction heuristic, alias carry-over
logic, `MemoryStoreConfig.merged_identities` round-trip. Integration: merge
endpoint end-to-end on real stores (files moved additively, journal deduped,
label/root moved, source retired, audit written), alias redirect on resolve
(remember at a merged identity's checkout lands in the survivor), scan with a
stubbed engine port (deterministic + engine tiers, no_model degradation),
CLI subcommands. Contract: OpenAPI drift. Acceptance markers on the four new
scenarios.
