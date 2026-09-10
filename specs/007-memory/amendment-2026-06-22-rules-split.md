# Amendment 2026-06-22 — recursive rules split

> **Historical — 2026-09-10.** Spec 006 (Knowledge Base) and spec 007 (Memory)
> merged into one **Knowledge Layer** on this date. [`spec.md`](./spec.md) is the
> authority for the merged model — one `knowledge` kind, three scopes, one
> storage root `~/.coffer/knowledge/<scope>/`, eight `coffer__*` tools. This
> document records the design as it stood before that merge; where it says
> "memory face", "`memory` kind", `~/.coffer/memory/`, `/api/v1/memory_stores`
> or `coffer memory …`, read the merged equivalents in `spec.md`. The folder
> name `specs/007-memory/` is likewise historical: it is the spec id every
> inbound link and the acceptance audit key on.

Status: **proposed** (design under review)
Amends: [spec 007 — Memory](./spec.md) · no new spec number (like the transcript-distillation extension)
Scope axis unchanged: the lanes (`knowledge` / `rules` / `handoff`) and files-as-truth (ADR-012/013) stay exactly as they are. This amendment only changes **how the rules lane partitions its files** and adds a **one-time stale-store cleanup**.

> The amendment originally also made the `journal` lane partition per day. The
> `journal` lane has since been removed (its only writer, transcript
> distillation, is gone), so that half is dropped; only the rules split below
> remains in force.
>
> **Also stale, 2026-09-10:** every mention below of a *rules bundle*, a
> *SessionStart bundle* or *injection* describes a delivery channel that no
> longer exists. The `coffer-hook` SessionStart hook, the `session-context`
> route and `RulesBundleAssembler` are deleted with FR-049/FR-050/FR-052/FR-055.
> The split itself, `read_all_rules`, and the concatenating read surface
> (`GET /api/v1/knowledge/{scope}/rules`, `coffer knowledge rules <scope>`) are
> unaffected and still in force — only the "and then it gets injected" half is
> gone.

## Motivation

1. The `rules` lane is a **single** `rules/rules.md`. As rules accumulate, one flat file does not scale for management. The user wants it to **stay a single file while small, then split itself into multiple files by topic as it grows** — recursively (a topic file that itself grows large splits again into sub-topic files).
2. The on-disk store at `~/.coffer/memory` predates the lane model (it used the old `type:` taxonomy — `user`/`feedback`/`project`/`reference`). It is stale relative to current `main` and is being removed so the lane code starts from a clean state.

## Out of scope

- No change to `knowledge` / `handoff` lanes, recall, sync, or the scope model.
- No re-merge of split rule files back into one when rules shrink (one-way split; YAGNI).
- No fixed category vocabulary — category slugs are chosen by the organizer's LLM.

## Change A — one-time stale-store cleanup (done)

The pre-lane `~/.coffer/memory/{global,projects}` tree was backed up to
`~/.coffer/memory-backup-2026-06-22.tar.gz` (71 files) and removed. The lane code
recreates the lane directory structure on first write. **No data migration** — the
old type-taxonomy store is not converted into lanes; its useful content is mirrored
in each project's Claude Code auto-memory.

This is a machine-local data operation, not a code change. Recorded here for traceability.

## Change B — rules: single file, recursive topic split

### Storage model
- **Small (≤ threshold rules in the lane):** unchanged — a single `rules/rules.md`.
- **Grown (> threshold in any single rules file):** the organizer's reorg pass runs an LLM **categorization** step that rewrites that file's rules into multiple `rules/<category>.md` files (one bullet list per file) and removes the now-split source file.
- **Recursive:** the same rule applies to any `rules/**/*.md`. A category file that itself exceeds the threshold splits again into `rules/<category>/<sub-topic>.md`. One uniform mechanism — "any rules file over threshold is re-categorized into finer files" — handles both the first split and every deeper level; no special-casing per level.
- **Threshold:** **100 rules** per file (count of bullets). Chosen on rule count (not bytes) because management bloat is driven by the number of entries; a dozen-to-~hundred rules read cleanly as one file, beyond that topic grouping earns its keep.
- Slugs are LLM-chosen, guarded as safe path segments (existing `_safe_segment`); nested dirs are allowed (`rules/git/commit.md`).

### Read surface (concatenation)
- New `read_all_rules(rules_dir)`: recursively globs `rules/**/*.md` (sorted) and concatenates them; if only the legacy single `rules/rules.md` exists, it reads that. Returns one markdown string.
- `session_context.get_rules` switches from `read_rules(rules_path(...))` to `read_all_rules(rules_dir(...))`. (At the time this also fed `RulesBundleAssembler`, which consumed one rules string per scope; that assembler is since deleted — `get_rules` now only backs the read endpoint.)
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

Rules:
- ≤ 100 rules → stays single `rules/rules.md`;
- crossing 100 in `rules.md` → reorg splits into `rules/<category>.md`, removes `rules.md`, total rule count preserved, no dupes;
- a category file crossing 100 → recursive split into `rules/<category>/<sub>.md`;
- `read_all_rules` concatenates all files (recursive) and falls back to legacy single file;
- a new rule after a split routes to the matching category file;
- ~~the injected SessionStart bundle still contains the rules + the two seeded built-in rules~~ — dropped with the injection channel (2026-09-10); the equivalent check is that the read surface returns every `rules/*.md` concatenated.

## Docs to update with the code (same change)

- `specs/007-memory/spec.md` + `spec.zh.md` — the amended FR (rules recursive split) and the affected scenarios (`rules/rules.md` → `rules/**/*.md`).
- `specs/007-memory/data-model.md` — storage layout (rules multi-file), organizer cascade, `get_rules`.

## Verification gates

`make verify` plus the Coffer-specific gates: `make lint` (file-size), `make verify-contract` (openapi↔model), `scripts/audit_acceptance.py` (scenario markers).
