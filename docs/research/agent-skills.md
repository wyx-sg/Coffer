# Competitive Research — Agent Skill Management & Distribution

> English: this file · 中文版: [agent-skills.zh.md](./agent-skills.zh.md)
>
> Internal competitive-research report for Coffer's skill manager (spec 005).
> **Date:** 2026-06-16. **Method:** deep-research harness (fan-out web search →
> source fetch → adversarial claim verification). **Provenance caveat:** the run
> fetched 21 sources and extracted 104 claims, but API rate-limiting during the
> verification/synthesis phase cut triple-verification short — 2 claims are
> 3-vote confirmed, the rest are single-primary-source (cited inline). Treat
> facts below as primary-sourced but flag for a light fact-check before any are
> quoted externally.

## 1. Landscape at a glance

The "agent skill" category barely existed before **Anthropic Agent Skills**
launched (~Oct 2025) and exploded once the format was published as the open
**agentskills.io** standard (repo `agentskills/agentskills` created 2025-12-16;
standard announced Dec 18, 2025; Apache-2.0 code + CC-BY-4.0 docs). The market
splits into four layers:

| Layer                         | What it is                                     | Examples                                                                                                                |
| ----------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Format / standard**         | The SKILL.md contract + progressive disclosure | Anthropic Agent Skills, agentskills.io open standard                                                                    |
| **First-party hosting**       | Vendor surfaces that store & run skills        | Claude.ai upload, Claude Developer Platform, Claude Code (filesystem)                                                   |
| **Cross-agent frameworks**    | One skill set installed into many agents       | obra/superpowers, ClaudeKit                                                                                             |
| **Registries / marketplaces** | Discovery + bulk distribution                  | tonsofskills.com (~2,800 skills), awesome-claude-skills, anthropics/skills, vercel-labs/skills, Smithery skill-packager |

### What a "skill" is

An Agent Skill is a filesystem directory built around a required `SKILL.md`
file with YAML frontmatter (`name`, `description`), using **three-level
progressive disclosure**: metadata always loaded (~100 tokens/skill at startup),
the `SKILL.md` body loaded only when the skill is triggered (<5k tokens
recommended, <500 lines), and bundled `scripts/`/`references/`/`assets/` loaded
only as needed (effectively unlimited, executed via bash without entering
context). [confirmed 3-0 — platform.claude.com/docs agent-skills/overview;
anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills]

The open standard fixes the frontmatter contract: `name` (≤64 chars, lowercase
alphanumeric + hyphens, **must match the parent directory name**) and
`description` (≤1024 chars) are required; `license`, `compatibility`,
`metadata`, and an experimental space-separated `allowed-tools` are optional.
**There is no built-in `version` field** — version is only an example metadata
key. [github.com/agentskills/agentskills]

### Distribution & portability

- **Portable in principle, siloed in practice.** Skills are portable across
  Anthropic's four surfaces (Claude.ai, Claude Code, Agent SDK, Developer
  Platform), but **custom skills do not sync across surfaces** — a skill
  uploaded to Claude.ai is not available on the API and vice versa, and Claude
  Code skills are filesystem-based and separate from both. [confirmed 3-0 —
  platform.claude.com]
- **Cross-vendor adoption is real.** The agentskills.io client showcase lists
  ~41 clients including Anthropic's competitors: Gemini CLI, Cursor, GitHub
  Copilot, OpenAI Codex, Goose, Mistral Vibe, Databricks, Snowflake, Letta,
  OpenHands, Spring AI. [github.com/agentskills/agentskills]
- **The dominant distribution rail is the Claude Code plugin marketplace.**
  Superpowers installs via `/plugin install superpowers@claude-plugins-official`
  (and per-harness equivalents for Codex, Cursor, Gemini CLI, Copilot CLI,
  OpenCode, Factory Droid). [github.com/obra/superpowers] ClaudeKit moved to a
  plugin-marketplace model in Dec 2025 (`/plugin marketplace add
mrgoonie/claudekit-skills`), gaining auto-updates and **deprecating manual
  git-clone install**; it ships 70+ skills in 13 categories as category bundles.
  [github.com/mrgoonie/claudekit-skills]
- **A real marketplace tier now exists.** tonsofskills.com (MIT) catalogs
  ~425–432 plugins and ~2,770–2,810 skills, gated by spec validation against the
  agentskills.io standard, with a CLI package manager `ccpi`
  (`@intentsolutionsio/ccpi`: search/install/list/update against a canonical
  `marketplace.json`). [github.com/jeremylongshore/claude-code-plugins-plus-skills]

### Security — the fastest-moving sub-theme

Anthropic provides **no built-in sandboxing or signing** for skill-bundled code;
security rests on a trust model ("install only from trusted sources; audit
untrusted skills"). [anthropic.com engineering blog; platform.claude.com] This
has spawned an active threat-research cottage industry in early 2026:

- **OWASP "Agentic Skills Top 10"** — a dedicated risk taxonomy. [owasp.org]
- **ToxicSkills** (Snyk) — malicious AI-agent skills distributed via a
  ClawHub-style channel. [snyk.io]
- **"Skill Issues: compromising Claude Code with malicious skills"** (Reversec,
  May 2026). [labs.reversec.com]
- **Scanner evasion** — a malicious-code test file reportedly **passed every
  one of Anthropic's skill scanners**. [venturebeat.com]
- Threat models from safedep.io and repello.ai.

This is the category's #1 unsolved problem and is directly relevant to Coffer.

## 2. Capability comparison

| Capability                       | Anthropic Agent Skills      | Superpowers                      | ClaudeKit          | tonsofskills / ccpi      | **Coffer skill manager**                     |
| -------------------------------- | --------------------------- | -------------------------------- | ------------------ | ------------------------ | -------------------------------------------- |
| Single source of truth           | Per-surface silos (no sync) | Plugin repo                      | Plugin marketplace | marketplace.json         | **`~/.coffer/skills/` master store**         |
| Cross-agent delivery             | Manual per surface          | Per-harness install (N installs) | Claude Code only   | Claude Code only         | **One store → many agents, reconciled**      |
| Delivery mechanism               | Upload / filesystem         | Plugin install                   | Plugin install     | CLI install              | **symlink / junction / copy per binding**    |
| Auto-distribute to all agents    | No                          | No                               | No                 | No                       | **"follow master library" + exclusions**     |
| Ingest hand-placed skills        | No                          | No                               | No                 | No                       | **unmanaged-skill scan + adopt**             |
| Discovery / browse               | Showcase                    | README                           | 13 categories      | ~2,800 skills            | **No (git URL / local path only)**           |
| Versioning / update              | No version field            | git pull                         | auto-update        | ccpi update              | git_ref pin, no update-detection UX          |
| Supply-chain hardening on ingest | Trust model only            | Trust model                      | Spec validation    | Spec validation          | **SSRF guard, depth-1, size cap, hooks off** |
| Signing / scanning               | None (scanners evadable)    | None                             | None               | Spec lint only           | **None (content not scanned)**               |
| Standard conformance             | Defines it                  | SKILL.md                         | agentskills.io     | agentskills.io validated | SKILL.md (not yet standard-aligned)          |

## 3. How Coffer compares

**Where Coffer is ahead.**

1. **Cross-agent delivery is a first-class, reconciled engine.** The ecosystem
   treats "one skill set across agents" as N separate installs (Superpowers) or
   doesn't do it at all. Coffer is the only design with one master store, a
   per-binding cross-platform link engine (symlink/junction/copy), and a
   **"follow the master library" policy** that auto-pushes the whole store
   (minus per-agent exclusions) to every agent. That directly solves the pain
   Anthropic documents ("custom skills do not sync across surfaces").
2. **Ingest safety is genuinely ahead of the field.** While the ecosystem is
   only now alarmed about malicious skills (ToxicSkills, OWASP Top 10,
   scanner-evasion), Coffer's git fetch already neutralizes the obvious
   supply-chain vectors: SSRF guard, shallow depth-1, clone-size cap, repo hooks
   neutralized, terminal-prompt disabled.
3. **"Adopt unmanaged skills" is unique.** Consolidating hand-placed skills back
   into a managed master store has no equivalent in any surveyed product.

**Where Coffer lags / should borrow.**

1. **No discovery.** The marketplaces (tonsofskills ~2,800 skills, ClaudeKit
   categories, agentskills.io showcase) set a browse-and-install bar Coffer
   doesn't meet — it requires the user to already know a git URL. A curated
   catalog or "import from agentskills.io / a marketplace.json" would close this.
2. **No update-detection / pinning UX.** Coffer stores a `git_ref` but has no
   "update available" signal; ClaudeKit/ccpi offer auto-update. Borrow:
   update-available detection and explicit pin/unpin.
3. **No trust layer beyond ingest.** Coffer hardens _fetching_ but does not
   _scan content_ — and the research shows the threat is the bundled scripts
   themselves, not the transport. A skill scanner (static checks on bundled
   code, `allowed-tools` enforcement, provenance display) would extend Coffer's
   head start into the category's #1 gap and fit its vault positioning.
4. **Not explicitly aligned to the agentskills.io standard.** Coffer already
   uses SKILL.md; adopting the standard's exact frontmatter constraints
   (name/description limits, `allowed-tools`) buys instant portability to the
   ~41-client ecosystem and lets Coffer ingest/redistribute standard skills
   verbatim.

## 4. Key takeaways for Coffer

1. **Conform to the agentskills.io open standard explicitly.** You already speak
   SKILL.md; adopting its frontmatter contract + `allowed-tools` makes every
   Coffer skill portable to ~41 clients and makes ingest/redistribute lossless.
2. **Lean into the differentiator.** "One library, every agent, no per-surface
   re-upload, auto-follow with exclusions" is something no competitor offers —
   market it as the headline.
3. **Build the trust layer (highest-leverage gap).** Skill supply-chain attacks
   (ToxicSkills, OWASP Top 10, scanner evasion) are the category's open wound.
   Your SSRF-hardened ingest is a head start; extend to content scanning +
   `allowed-tools` enforcement + provenance — this is on-mission for a "vault."
4. **Add discovery + update detection.** A curated catalog / marketplace import
   and an "update available" signal close the two UX gaps versus
   tonsofskills/ClaudeKit without changing your master-store model.

## 5. Sources

Primary:

- platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- github.com/agentskills/agentskills · agentskills.io/home
- github.com/anthropics/skills
- github.com/obra/superpowers
- github.com/mrgoonie/claudekit-skills
- github.com/jeremylongshore/claude-code-plugins-plus-skills
- github.com/vercel-labs/skills · github.com/travisvn/awesome-claude-skills
- smithery.ai/skills/shawn-sandy/skill-packager

Security:

- owasp.org/www-project-agentic-skills-top-10/
- labs.reversec.com/posts/2026/05/skill-issues-compromising-claude-code-with-malicious-skills-agents-part-1
- snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/
- venturebeat.com/security/anthropic-skill-scanners-passed-every-check-malicious-code-test-file
- safedep.io/agent-skills-threat-model/ · repello.ai/blog/claude-code-skill-security

Commentary:

- simonwillison.net/2025/Dec/19/agent-skills/
- unite.ai — "Anthropic Opens Agent Skills Standard"

## Verification update (2026-06-19)

> Light fact-check pass against primary sources: 1 local claim and 3 web claims
> verified. All hold up; one web claim needs a framing fix (the scanners are
> third-party, not Anthropic-built). **Re-verified 2026-06-19 against
> `main` after PR #105 (frontmatter alignment), PR #111 (skill content
> trust layer), and PR #115 (skill update detection + pinning) merged:**
> §2/§3/§4's "no skill scanner / content not scanned" headline gap is now
> **closed** (#111), the §4 "no update-detection / pinning UX" gap is now
> **closed** (#115, see ✏️ below), and the frontmatter-alignment status is
> refined below (#105 capped `description` and recognized `allowed-tools` but
> kept the underscore as a deliberate backward-compat superset).

### ✅ Confirmed

- **Coffer pins a skill's source to a `git_ref`.** `GitSource` carries
  `git_url`/`git_ref`/`git_subpath` (`repo:backend/coffer/domain/skill/source.py`),
  and a fetch/clone resolves and copies exactly that ref into the master store
  (spec FR-006). This pinning fact still holds on `main`; the report's
  accompanying claim that there is **no** update-detection / out-of-date signal
  is now stale — PR #115 added one (see ✏️ below).
  [`repo:backend/coffer/domain/skill/source.py`,
  `repo:specs/005-skill-manager/{spec,plan}.md`]
- **SKILL.md frontmatter is now aligned to the agentskills.io constraints
  (PR #105, 2026-06-18) — partially.** As of #105, `SkillFrontmatter`
  enforces the standard's caps (`name` ≤64, `description` ≤1024) and now
  **recognizes and retains** the optional `license` and experimental
  `allowed-tools` fields rather than dropping them under `extra="allow"`
  (`allowed-tools` is normalized to a list and is the data the trust layer
  consumes). Two gaps the report flagged remain by design, not omission: it
  still does **not** enforce `name == parent-directory`, and the `name` regex
  still tolerates underscores (see ✏️ below). [`repo:backend/coffer/domain/skill/frontmatter.py`,
  `repo:specs/005-skill-manager/{spec,data-model,plan}.md`, spec FR-004/FR-027]
- **Reversec "Skill Issues" post is real and as described.** "Skill Issues:
  Compromising Claude Code with malicious skills & agents — Part 1," James
  Henderson, published **May 5, 2026** (report's "May 2026" is correct). Thesis
  matches: skills/agents are executable instructions with file/command access,
  comparable to running untrusted binaries / pip packages; RCE pathways include
  the `allowed-tools` frontmatter and agent permission overrides.
  [labs.reversec.com/posts/2026/05/skill-issues-compromising-claude-code-with-malicious-skills-agents-part-1]
- **agentskills.io frontmatter constraints are exact.** `name` required, ≤64
  chars, lowercase `a-z`/`0-9`/hyphens only (no leading/trailing or consecutive
  hyphens) **and must match the parent directory name**; `description` required,
  ≤1024 chars, non-empty; **no top-level `version` field** (the only `version`
  is inside the optional `metadata` example); `allowed-tools` is an optional
  space-separated string explicitly marked "(Experimental)."
  [agentskills.io/specification]

### ✏️ Corrected

- **§1 Security / §5 Sources framing of the scanner-evasion story.** Old: "a
  malicious-code test file reportedly passed every one of **Anthropic's** skill
  scanners." Corrected: the scanners are **third-party** tools that audit
  Anthropic/Claude skills — **Snyk Agent Scan, Cisco's AI Agent Security
  Scanner, and VirusTotal Code Insight** — not scanners built by Anthropic. The
  substance holds: a payload bundled in a `*.test.ts` file passed all of them
  because none inspects bundled test files as an execution surface (test files
  run with full local permissions via standard test runners / `npm test` / CI).
  Underlying research attributed to Gecko Security (surfaced via CrowdStrike at
  RSAC 2026).
  [venturebeat.com/security/anthropic-skill-scanners-passed-every-check-malicious-code-test-file]
- **Internal nit: §1 says `name` is "lowercase alphanumeric + hyphens," but
  Coffer's regex `^[a-z0-9][a-z0-9_-]{0,63}$` also permits underscores**, which
  the standard does not. PR #105 (frontmatter alignment) did **not** remove the
  underscore — it is now documented in-code and in spec FR-004 as a _deliberate
  backward-compat superset_ (to keep skills already on disk valid), so the
  divergence stands by design, not as an oversight. [`repo:backend/coffer/domain/skill/frontmatter.py`,
  spec FR-004, agentskills.io/specification]
- **§2/§3/§4's headline "no skill scanner / content not scanned" gap is now
  CLOSED (PR #111, 2026-06-18 — skill content trust layer L2).** The report's
  capability table marked Coffer "None (content not scanned)" and named a
  content scanner as the highest-leverage missing piece. Coffer now ships a
  heuristic content scanner: `scan_skill_folder` walks a skill's text files and
  applies single-line regex rules for remote-exec pipes (`curl|wget … | sh`),
  base64/obfuscated payloads, secret/credential access (`~/.ssh`, `~/.aws`,
  `id_rsa`, `AWS_SECRET_ACCESS_KEY`), dangerous recursive `rm`, shell `eval`,
  network egress, and privilege escalation, yielding a verdict
  (`low`/`medium`/`high`/`critical` or none). It runs on **every ingest**
  (import, fetch, adopt) and every content-changing op (update/edit), caches
  the verdict on `SkillConfig`, and a **`high`/`critical` verdict gates
  enabling a skill for an agent until the user explicitly acknowledges the risk
  (409; follow/auto-bind reconcilers skip un-acked skills)**. It is explicitly
  advisory and non-authoritative — Coffer delivers but never executes skills,
  so a clean report is not a safety guarantee (ADR-027). Note this is Coffer's
  _own_ scanner; it is unrelated to the external scanner-evasion story above
  (Snyk/Cisco/VirusTotal), which concerns third-party auditors missing payloads
  in bundled test files. [`repo:backend/coffer/domain/skill/content_scan.py`,
  `repo:backend/coffer/domain/skill/config.py`,
  `repo:backend/coffer/application/skill/{scan_ops,lifecycle_ops,update_ops,binding_ops}.py`,
  `repo:backend/coffer/surfaces/http/skill_routes.py`, spec FR-028/FR-029,
  `repo:docs/decisions/ADR-027-skill-content-trust-layer.md`]
- **§4's "no update-detection / pinning UX" gap is now CLOSED (PR #115,
  2026-06-18 — skill update detection + pinning).** The report listed
  "no 'update available' signal" as one of the two UX gaps versus
  ClaudeKit/ccpi and recommended exactly "update-detection + explicit
  pin/unpin." Coffer now ships both. An on-demand `check_for_updates`
  (spec FR-030) re-fetches a Git-sourced skill at its pinned `git_ref`,
  re-validates the upstream SKILL.md, and compares the upstream content hash
  (and frontmatter `name`, to catch renames) against the stored
  `version_hash` — **without applying anything** — then caches the result
  (`update_available`, `available_version_hash`, `last_update_check_at`) on
  `SkillConfig`; applying an update clears the signal, and every check is
  audited (`skill_update_checked`). A `pinned` flag (spec FR-031,
  `coffer skill pin`/`unpin`, audited `skill_pinned`/`skill_unpinned`)
  suppresses the signal so a deliberately-frozen skill stops surfacing as
  out-of-date; `SkillOut` exposes the resolved `update_pending =
  update_available and not pinned`. It is surfaced across all three surfaces:
  `POST /skills/{name}/check-update` · `/pin` · `/unpin` (HTTP), the
  `coffer skill check-update`/`pin`/`unpin` CLI plus an `update:` row in
  `skill show`, and an update row on the desktop skill detail. Local-imported
  skills cannot be checked (`UpdateNotSupported` — re-import to refresh), and
  `plan.md`'s deferral now scopes only to commit-level pinning / multi-version
  coexistence, not update detection. [`repo:backend/coffer/application/skill/update_ops.py`,
  `repo:backend/coffer/domain/skill/config.py`,
  `repo:backend/coffer/surfaces/http/skill_trust_routes.py`,
  `repo:backend/coffer/surfaces/cli/skill_cmd.py`,
  `repo:frontend/src/components/skills/SkillDetailTabs.tsx`,
  spec FR-030/FR-031]
