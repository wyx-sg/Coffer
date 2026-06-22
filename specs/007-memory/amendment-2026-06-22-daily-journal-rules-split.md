# Amendment 2026-06-22 — daily journal files + recursive rules split

Status: **proposed** (design under review)
Amends: [spec 007 — Memory](./spec.md) · no new spec number (like the transcript-distillation extension)
Scope axis unchanged: the four lanes (`knowledge` / `rules` / `journal` / `handoff`) and files-as-truth (ADR-012/013) stay exactly as they are. This amendment only changes **how two lanes partition their files** and adds a **one-time stale-store cleanup**.

## Motivation

1. The `journal` lane partitions one file **per month** (`journal/<YYYY-MM>.md`). The user wants **per-day** files (`journal/<YYYY-MM-DD>.md`), and a day with no entry must **not** create a file.
2. The `rules` lane is a **single** `rules/rules.md`. As rules accumulate, one flat file does not scale for management. The user wants it to **stay a single file while small, then split itself into multiple files by topic as it grows** — recursively (a topic file that itself grows large splits again into sub-topic files).
3. The on-disk store at `~/.coffer/memory` predates the lane model (it used the old `type:` taxonomy — `user`/`feedback`/`project`/`reference`). It is stale relative to current `main` and is being removed so the lane code starts from a clean state.

## Out of scope

- No change to `knowledge` / `handoff` lanes, recall, sync, or the scope model.
- No re-merge of split rule files back into one when rules shrink (one-way split; YAGNI).
- No fixed category vocabulary — category slugs are chosen by the organizer's LLM.
- No pagination of the `/journal` read endpoint (it already returns all period files; daily granularity makes the list longer but the shape is unchanged).

## Change A — one-time stale-store cleanup (done)

The pre-lane `~/.coffer/memory/{global,projects}` tree was backed up to
`~/.coffer/memory-backup-2026-06-22.tar.gz` (71 files) and removed. The lane code
recreates the lane directory structure on first write. **No data migration** — the
old type-taxonomy store is not converted into lanes; its useful content is mirrored
in each project's Claude Code auto-memory.

This is a machine-local data operation, not a code change. Recorded here for traceability.

## Change B — journal: per-day files, no empty files

### New / changed behaviour
- `journal_period(when)` partitions **per day**: `when.strftime("%Y-%m-%d")` → `journal/<YYYY-MM-DD>.md`.
- `journal_doc_id(period)` is unchanged in shape (`journal-<period>`), now `journal-2026-06-22`. Per-day → one indexable `documents` row per day (finer recall granularity; accepted).
- **Empty-body guard**: `JournalService.append` and `journal_files.append_entry` treat a blank/whitespace-only body as a **no-op** — nothing is written, so no file is created. This satisfies "a day with no entry creates no file" (files are only ever created by a real append) and removes the one accumulation path the lane had (the journal was the only lane without an empty-write guard).
- `scan_journal_dir` / `_indexable_body` are granularity-agnostic and need no change.

### Contract / API delta
- `JournalFileOut.period` semantics change from `YYYY-MM` to `YYYY-MM-DD` (same `str` type). Update the description in `contracts/api.openapi.yaml` and `data-model.md`. `JournalOut.files` stays "newest period first" (date-string sort is still correct).
- The `/api/v1/memory_stores/{name}/journal` read surface is otherwise unchanged.

### Frontend
- The Journal tab lists period files newest-first and renders each file's markdown. Daily files only make the list longer; the DTO shape is unchanged, so **no frontend change is expected** — to be confirmed by running the four-lane store UI.

## Change C — rules: single file, recursive topic split

### Storage model
- **Small (≤ threshold rules in the lane):** unchanged — a single `rules/rules.md`.
- **Grown (> threshold in any single rules file):** the organizer's reorg pass runs an LLM **categorization** step that rewrites that file's rules into multiple `rules/<category>.md` files (one bullet list per file) and removes the now-split source file.
- **Recursive:** the same rule applies to any `rules/**/*.md`. A category file that itself exceeds the threshold splits again into `rules/<category>/<sub-topic>.md`. One uniform mechanism — "any rules file over threshold is re-categorized into finer files" — handles both the first split and every deeper level; no special-casing per level.
- **Threshold:** **100 rules** per file (count of bullets). Chosen on rule count (not bytes) because management bloat is driven by the number of entries; a dozen-to-~hundred rules read/inject cleanly as one file, beyond that topic grouping earns its keep.
- Slugs are LLM-chosen, guarded as safe path segments (existing `_safe_segment`); nested dirs are allowed (`rules/git/commit.md`).

### Read surface (concatenation)
- New `read_all_rules(rules_dir)`: recursively globs `rules/**/*.md` (sorted) and concatenates them; if only the legacy single `rules/rules.md` exists, it reads that. Returns one markdown string.
- `session_context.get_rules` switches from `read_rules(rules_path(...))` to `read_all_rules(rules_dir(...))`. The `RulesBundleAssembler` injection logic is **unchanged** (it still consumes one rules string per scope).
- The `GET /api/v1/memory_stores/{name}/rules` read surface returns the concatenated markdown (per-file sections), so its DTO shape is unchanged.

### Write paths (post-split routing)
- `append_rule` today appends to the single `rules_path`. After a split, a freshly-classified rule must land in the right file: the organizer (`organizer.py`) and reorg promotion (`reorg.py`) classify the new rule's category and append to the matching `rules/<category>.md` (creating it when new), preserving idempotent dedup and atomic write per file.
- The split itself lives in the reorg pass (`reorg.py`) — the existing LLM consolidation step that already classifies items and writes rules — not in the hot `append_rule` path.

### Contract / API delta
- `data-model.md`: the rules-lane description, the organizer cascade row, and the `get_rules` read surface change from "the single `rules/rules.md`" to "the `rules/**/*.md` files (concatenated)".
- No OpenAPI schema field changes for rules (the read still returns markdown text); only prose.

### Frontend
- The Rules tab renders the rules document. Because the read API still returns one concatenated markdown blob, **no frontend change is expected** — to be confirmed in the UI run.

## Test plan (TDD)

Journal:
- empty/whitespace body → no file created, no `documents` row;
- two entries same day → one `journal/<YYYY-MM-DD>.md` with both entries;
- entries on different days → separate per-day files;
- `period` surfaced as `YYYY-MM-DD`; `/journal` lists newest-day first.

Rules:
- ≤ 100 rules → stays single `rules/rules.md`;
- crossing 100 in `rules.md` → reorg splits into `rules/<category>.md`, removes `rules.md`, total rule count preserved, no dupes;
- a category file crossing 100 → recursive split into `rules/<category>/<sub>.md`;
- `read_all_rules` concatenates all files (recursive) and falls back to legacy single file;
- a new rule after a split routes to the matching category file;
- the injected SessionStart bundle still contains the rules + the two seeded built-in rules.

## Docs to update with the code (same change)

- `specs/007-memory/spec.md` + `spec.zh.md` — two amended FRs (journal per-day; rules recursive split) and the affected scenarios (`rules/rules.md` → `rules/**/*.md`).
- `specs/007-memory/data-model.md` — storage layout (`journal/<YYYY-MM-DD>.md`; rules multi-file), organizer cascade, `get_rules`, `JournalFileOut.period`.
- `specs/007-memory/contracts/api.openapi.yaml` — `JournalFileOut.period` description (`make verify-contract` gate).

## Verification gates

`make verify` plus the Coffer-specific gates: `make lint` (file-size), `make verify-contract` (openapi↔model), `scripts/audit_acceptance.py` (scenario markers).
