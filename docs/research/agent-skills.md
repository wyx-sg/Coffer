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
