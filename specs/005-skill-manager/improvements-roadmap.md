# Skill Manager — Improvements Roadmap

Status: planning. Derived from the competitive-landscape research in
[`docs/research/agent-skills.md`](../../docs/research/agent-skills.md) (Report #3
in [`docs/research/README.md`](../../docs/research/README.md)). The research
ranks Coffer ahead on cross-agent delivery and SSRF-hardened ingest, and behind
on four points. This roadmap turns those four points into sequenced, PR-sized
work on top of the shipped 005 skill manager.

The Chinese mirror is [`improvements-roadmap.zh.md`](./improvements-roadmap.zh.md).

## Sequencing

```
#4 frontmatter alignment  →  #3 trust layer (L2)  →  #2 update detection / pinning  →  #1 discovery
   (small, prerequisite)      (large, top-leverage)    (medium, independent)            (large, reuses #3/#4)
```

Dependency rationale:

- **#4 first** — recognizing the `allowed-tools` frontmatter field is the data the
  trust layer (#3) consumes.
- **#1 last** — browse-and-install reuses the existing git-fetch ingest path, which
  must already carry #3's content scan and #4's validation before discovery rides
  on top of it.
- **#2 and #3** are mutually independent and may be swapped; for a faster stream of
  shippable wins, run 4 → 2 → 3 → 1.

Each item is one branch / one PR, spec-first: update `spec.md`/`spec.zh.md`,
`data-model.md`, `contracts/api.openapi.yaml`, then implement with tests, then
`make verify`.

## #4 — agentskills.io frontmatter alignment (this PR)

**Gap.** `SkillFrontmatter` enforced only `name` + `description` presence;
`description` had no length cap (the standard says ≤1024), and optional standard
fields (`license`, experimental `allowed-tools`) were silently dropped under
`extra="allow"`.

**Change.** Cap `description` at 1024 chars (hard 422, same path as the existing
`name`-too-long failure); recognize and retain `license` and `allowed-tools`
(lenient coercion: list or delimited string → normalized list; malformed →
tolerated as absent). Spec: FR-004 amended, FR-027 added, two acceptance
scenarios. `name` keeps its documented superset of the standard charset
(underscore tolerated) for backward-compatibility.

**Out of scope (deferred to #2/verify).** Enforcing the standard's
"name == parent directory" rule for in-store skills — Coffer normalizes the
master folder to `<name>` on write, so this only bites a verify-time
consistency check, which belongs with #2.

## #3 — Trust layer, level L2 (heuristic scan + warn)

The research's #1 highest-leverage gap, and on-mission for a vault. **Boundary:**
Coffer delivers skills but never runs them, so it cannot enforce `allowed-tools`
at runtime (the host agent does). Coffer's "trust" is gate-at-ingest/enable plus
making risk legible. Records a new ADR.

- **L1 inventory + provenance.** Enumerate scripts/executables (extension +
  shebang + exec bit) with path/size/sha256; read declared `allowed-tools`;
  surface source URL, `git_ref`, ingest time, `version_hash` (already stored).
- **L2 heuristic scan.** Pure `scan_skill_folder(folder) -> list[Finding]`
  (`severity`, `rule_id`, `file`, `line?`, `message`). Rules: dangerous shell
  (`curl … | sh`, `eval`, base64→exec, `rm -rf`, sudo, writes outside the
  folder), network egress, suspected exfil (`~/.ssh`, `~/.aws`, env dumps piped
  out), `allowed-tools` vs. observed behavior mismatch (best-effort), obfuscation
  (long base64/hex blobs).
- **Non-blocking.** Ingest/enable proceed; a verdict ≥ high marks the skill
  "needs acknowledgment" and binding/enable requires an explicit ack
  (`POST /skills/{name}/acknowledge-risk`, audited). Scan runs at import,
  git-fetch, and update-apply; results persist on `SkillConfig`
  (`scan_verdict`, `findings_count`, `last_scanned_at`, `ruleset_version`).
- **Surfaces.** Detail-page findings, list badge, `SKILL_SCANNED` /
  `SKILL_RISK_ACKNOWLEDGED` audit events, CLI `coffer skill scan <name>`.

## #2 — Update detection + pinning

`update_ops.apply_update` already compares the SKILL.md hash, but only as a
pull-and-apply. Add:

- `check_for_updates(ref)` — re-fetch the source (shallow, via `source_fetcher`),
  validate, compute the candidate hash, compare without applying; return
  `UpdateStatus {available, current_hash, available_hash, rename_detected}`.
- Cache fields on `SkillConfig` (`update_available`, `last_update_check_at`,
  `available_version_hash`) for a list badge.
- Pinning: a branch `source.ref` follows; a tag/sha is pinned. `pin_to_resolved`
  rewrites `source.ref` to the current commit sha; pinned skills don't nag.
- On-demand only (button / `coffer skill check-updates`); no periodic poll in v1
  (local-first). Folds in the verify-time name==dir check from #4.
- Surfaces: `POST /skills/{name}/check-update`, list field, CLI, UI badge.

## #1 — Discovery (browse-and-install)

Currently requires a known git URL; rivals offer browse-and-install catalogs.

- `CatalogSource` port. v1: a curated static catalog (bundled JSON or a pinned
  index URL) of `{name, description, git URL, ref, publisher}`; optionally known
  registries (anthropics/skills, vercel-labs/skills, agentskills.io API if
  stable). Remote index fetch is allowed (local-first ≠ no remote calls), kept
  opt-in / refreshable.
- Install reuses the git-fetch ingest path (SSRF guard + validate + #3 scan), so
  discovery rides on #3/#4. Cross-references #2 for "newer version available".
- Surfaces: `GET /catalog/skills`, `POST /catalog/refresh`, UI catalog page, CLI
  `coffer skill search`.

## Positioning (non-code, ships with #3)

Lead with the differentiator the research highlights: "one library, every agent,
no per-surface re-upload, auto-follow with exclusions — and every skill is
scanned on ingest." Update `docs-site/guide/skills.md` and the README once the
trust layer makes the claim true.
