# Agent skills: how other products do it

**Feature**: author or import agent skills (`SKILL.md` bundles) once, deliver them into several coding agents, and keep what gets delivered intact and safe to load · **Coffer spec**: [skill-manager](../../openspec/specs/skill-manager/spec.md) · **Related ADRs**: [cross-platform-skill-delivery](../decisions/cross-platform-skill-delivery.md), [coffer-ships-its-own-skill](../decisions/coffer-ships-its-own-skill.md), [per-agent-resource-scope](../decisions/per-agent-resource-scope.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (docs, repos, source files, vendor security write-ups), checked 2026-09-24

Star counts are as of 2026-09 and taken from the GitHub page on the check date.

---

## 1. The format everyone targets: the Agent Skills open standard

Anthropic shipped Agent Skills in Claude in October 2025 and published the format
as an open standard at [agentskills.io](https://agentskills.io/home) in December
2025 (repo [`agentskills/agentskills`](https://github.com/agentskills/agentskills)).
The spec defines only what goes inside a skill folder. It does not say where skills
live on disk, how they are installed, or how they are versioned. Those gaps are
where the distribution tools below compete.

**Folder layout** ([specification](https://agentskills.io/specification)):

```
skill-name/
├── SKILL.md       required: YAML frontmatter + Markdown body
├── scripts/       optional: executable code
├── references/    optional: docs loaded on demand
├── assets/        optional: templates, data, images
└── ...            anything else
```

**Frontmatter**:

| Field | Required | Constraint |
| --- | --- | --- |
| `name` | yes | 1–64 chars; `a-z`, `0-9`, `-`; no leading/trailing or consecutive hyphens; **must match the parent directory name** |
| `description` | yes | 1–1024 chars; should say both what the skill does and when to use it |
| `license` | no | licence name or bundled licence file |
| `compatibility` | no | 1–500 chars; environment requirements |
| `metadata` | no | string→string map for client-specific extras (the spec's own example puts `version` here) |
| `allowed-tools` | no | space-separated pre-approved tools, marked *Experimental* |

The spec has no top-level `version`, no integrity hash, no signature, no dependency
field and no permission manifest. Validation is `skills-ref validate ./my-skill`
from the reference library.

**Progressive disclosure**, the core loading contract:

1. *Metadata* (~50–100 tokens per skill): `name` + `description` for every skill, loaded at session start.
2. *Instructions* (<5,000 tokens recommended, keep `SKILL.md` <500 lines): full body, loaded on activation.
3. *Resources*: files in `scripts/`, `references/`, `assets/`, loaded or run only when the body points at them. References should stay one level deep.

**Client implementation guide.** The standard also publishes a guide for agent
authors ([adding skills support](https://agentskills.io/client-implementation/adding-skills-support)).
Several of its recommendations shape how distribution tools behave:

- Scan both a client-specific directory and the cross-client convention in each
  scope: `<project>/.<client>/skills/`, `<project>/.agents/skills/`,
  `~/.<client>/skills/`, `~/.agents/skills/`. It notes that some clients also scan
  `.claude/skills/` "for pragmatic compatibility".
- Bound the scan: skip `.git/` and `node_modules/`, cap depth at 4–6 levels and at
  about 2,000 directories.
- Project-level beats user-level on a name collision. Log a warning when one skill
  shadows another.
- Parse leniently. Retry YAML with an unquoted colon in a value by quoting it. If
  the name does not match the directory or is too long, warn but still load. If
  the description is missing or the YAML cannot be parsed at all, skip the skill.
  This relaxes the spec's own strict `name` rules on purpose.
- **Trust gate.** A freshly cloned repository can bring project-level skills with
  it, so load them only for trusted folders.
- Leave disabled or `disable-model-invocation` skills out of the catalog entirely.
  Don't list them and then block them at activation.
- Exempt activated skill content from context compaction, and skip loading a skill
  that is already active.

**Adoption.** On 2026-09-24 the client showcase on agentskills.io lists 46 products.
They include Claude Code, Claude, ChatGPT & Codex, Gemini CLI, Cursor, GitHub
Copilot, VS Code, OpenCode, OpenHands, Goose, Amp, Kiro, Roo Code, Junie, Factory,
Letta, TRAE, Mistral Vibe, Databricks, Snowflake, Spring AI, Hermes Agent and
OpenClaw ([home page source](https://agentskills.io/home)). The standard is now the
common format for skills, and each client's own frontmatter extensions sit on top of it.

---

## 2. How the target agents discover and load skills

### 2.1 Claude Code

Source: [Claude Code skills docs](https://code.claude.com/docs/en/skills).

**Discovery roots and precedence.** The command name comes from the directory
name. For personal and project skills, `name` only sets the display label.

| Scope | Path | Notes |
| --- | --- | --- |
| Enterprise / managed | `.claude/skills/` in the managed-settings dir | highest precedence |
| Personal | `~/.claude/skills/<name>/SKILL.md` | beats project on a name clash |
| Project | `.claude/skills/<name>/SKILL.md` | walks the session dir and its parents up to the repo root; in a git worktree it stops at the worktree root but can fall back to the main checkout's skills |
| Nested | `<subdir>/.claude/skills/` | loaded the first time Claude edits files in that subdir; a clash becomes a qualified `/apps/web:deploy` |
| `--add-dir` | `.claude/skills/` inside the added dir | |
| Plugin | `<plugin>/skills/<name>/SKILL.md` | always namespaced `/<plugin>:<skill>` |
| claude.ai-synced | `~/.claude/skills/synced/` | synced skills are downloaded at startup and checked about every 10 minutes. A synced skill whose name clashes runs as `/anthropic-skills:<name>`. Shell injection is disabled in synced skills. `syncClaudeAiSkills: false` turns syncing off |

A skill beats a legacy `.claude/commands/<name>.md` of the same name. Local skills
beat bundled ones, except for bundled aliases.

**Symlinks.** The docs say a `<skill-name>` entry in the enterprise, personal or
project location "can be a symlink to a directory elsewhere on disk. Claude Code
reads `SKILL.md` from the target and loads the skill once even if several locations
point at the same target." In practice, symlink handling has regressed more than
once. Reports include:

- `~/.claude/skills` itself being a symlink stopped loading user skills around
  v2.1.69, which shipped symlink-related security fixes
  ([#38051](https://github.com/anthropics/claude-code/issues/38051)).
- `/skills` and autocomplete not listing symlinked skills that still worked through
  the Skill tool ([#14836](https://github.com/anthropics/claude-code/issues/14836),
  [#36659](https://github.com/anthropics/claude-code/issues/36659)).
- Symlinked skills failing validation but running anyway
  ([#25367](https://github.com/anthropics/claude-code/issues/25367)).

Symlink the individual `<skill-name>` entry, not the whole `skills/` directory. That
is the pattern the docs support.

**Claude Code frontmatter**, a superset of the standard: `when_to_use`,
`disable-model-invocation`, `user-invocable`, `argument-hint`, `arguments`,
`context: fork` + `agent`, `model`, `effort`, `shell`, `allowed-tools`,
`disallowed-tools`, `paths` (globs that gate when the skill loads), `hooks`, plus
the standard's `license`, `compatibility` and `metadata`. The body supports:

- `` !`cmd` `` and ```` ```! ```` blocks, which run before the model sees the body
  (2-minute timeout; a non-zero exit aborts the skill;
  `disableSkillShellExecution` turns them off).
- `$ARGUMENTS`, `$N` and named-argument substitution.
- `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_PLUGIN_ROOT}` placeholders.

**`allowed-tools` semantics** matter for safety. The field pre-approves the listed
tools for the current turn only, and it does **not** restrict any other tool. It
also applies in `-p` runs on untrusted repos without workspace trust. So a skill's
`allowed-tools` can widen what runs without a prompt.

**Context budget.**

- Each skill's `description` + `when_to_use` is truncated at **1,536 characters** in the listing.
- The whole listing is capped at a fraction of the context window. The setting is
  `skillListingBudgetFraction`, default `0.01`, i.e. 1%. When the listing overflows,
  descriptions are dropped starting with the least-invoked skills. Every name stays.
- A bug report says the fraction was computed against a fixed ~200K baseline rather
  than a 1M window. It was closed as a duplicate on 2026-05-11
  ([#57941](https://github.com/anthropics/claude-code/issues/57941)).
- After compaction, invoked skills are re-attached. Each keeps its first 5,000
  tokens, with a combined cap of 25,000 tokens, and the most recent skills win.
- `/doctor`, `/context` and `/skill-doctor` report listing cost and usage.

**Lifecycle.** Skill directories are watched, so edits to `SKILL.md` apply
mid-session. A skills root that did not exist at startup needs a restart. Plugin
parts (hooks, MCP) need `/reload-plugins`. Access can be gated with permission rules
(`Skill(deploy *)`) and per-skill `skillOverrides` (`on` / `name-only` /
`user-invocable-only` / `off`).

### 2.2 Codex

Sources: [Codex "Build skills" docs](https://learn.chatgpt.com/docs/build-skills) (formerly developers.openai.com/codex/skills), [openai/skills](https://github.com/openai/skills) (27.6k★), [openai/codex PR #11289](https://github.com/openai/codex/pull/11289).

**Roots**, scanned in this order:

1. Repo: `.agents/skills`, from the cwd up to the repo root.
2. User: `$HOME/.agents/skills`.
3. Admin: `/etc/codex/skills`.
4. System: skills bundled with Codex.

`$CODEX_HOME/skills` (i.e. `~/.codex/skills`) is **deprecated but still read** for
backward compatibility. `CODEX_HOME` does not move the `.agents` root. A PR adding
`AGENTS_HOME` to relocate it was closed unmerged in February 2026, when OpenAI moved
to invitation-only contributions (PR #11289). When two roots hold the same name,
both skills appear in the selector. Codex does not merge them or pick one silently.
The docs say symlinked skill folders are supported in every location.

**Invocation and budget.** The user can invoke a skill explicitly with `$skill` in
the CLI/IDE (`@` in ChatGPT), or the model can pick it implicitly. The initial skills
list may take up to **2% of the context window**, or 8,000 characters when the
window size is unknown. When skills overflow, descriptions are shortened first, and
very large sets drop skills with a warning.

**Codex-specific metadata** lives in a sidecar `agents/openai.yaml` inside the skill,
not in the standard frontmatter. It holds display name, icon, brand colour,
`allow_implicit_invocation: false`, and declared tool dependencies such as required
MCP servers. You disable a skill locally with a `[[skills.config]]` entry with
`enabled = false` in `~/.codex/config.toml`.

**Install.** `$skill-installer <name>` is itself a skill. It pulls from
`openai/skills`, whose tiers are `.system` (auto-installed), `.curated` and
`.experimental`. The installer docs say to restart Codex afterwards. The
`openai/skills` repo is now marked deprecated in favour of the OpenAI Plugins
repository, so Codex is moving skill distribution into plugins the way Claude Code did.

**Migration.** Codex 0.128–0.130 added a `migrate-to-codex` skill. It converts Claude
Code skills and commands into `.agents/skills` packages. It skips runtime expansions
it cannot convert statically: `$ARGUMENTS`, `$1`, `@file`
([write-up](https://codex.danielvaughan.com/2026/05/13/codex-cli-agent-migration-system-import-claude-code-sessions-skills-config/)).

**Known failure.** In April 2026, users reported that skills in `~/.agents/skills`,
`~/.codex/skills` and symlinked locations stopped appearing in new sessions after an
update. Codex desktop and the VS Code extension were affected. No official fix was
posted in the thread
([forum thread](https://community.openai.com/t/local-skills-in-agents-skills-are-no-longer-discovered-in-new-codex-sessions/1379522)).
Even with discovery working, a changed skill appears only after a restart.

### 2.3 Cursor

Source: [Cursor skills docs](https://cursor.com/docs/context/skills).

**Roots.** Project: `.agents/skills/`, `.cursor/skills/`. User: `~/.agents/skills/`,
`~/.cursor/skills/`. Cursor also reads Claude and Codex locations for legacy
compatibility: `.claude/skills/`, `.codex/skills/`, `~/.claude/skills/`,
`~/.codex/skills/`. Discovery is recursive. A project skill in a subfolder is scoped
to that folder, which is how monorepos work.

**Frontmatter and invocation.** Cursor adds `paths`, `disable-model-invocation`,
`icon` and `color` to the standard fields. A skill can be invoked automatically, via
`/` search, or as a session-wide "Custom Mode".

**No direct remote import.** The docs say: "Skills aren't imported on their own. To
bring skills in from a GitHub repository, package them in a plugin and publish that
plugin through a marketplace."

### 2.4 Gemini CLI

Source: [Gemini CLI skills docs](https://geminicli.com/docs/cli/skills/).

**Precedence**, lowest first:

1. Built-in.
2. Extension.
3. User: `~/.gemini/skills/` or `~/.agents/skills/`.
4. Workspace: `.gemini/skills/` or `.agents/skills/`.

On a name clash the higher tier wins.

**Activation takes consent.** The model calls an `activate_skill` tool. The user
then sees a **confirmation prompt showing the skill's details and file-access scope**
before the body loads. This is the only major agent surveyed that puts a consent
step on activation.

**Management.** In a session: `/skills list|enable|disable|link <path>`. From the
shell: `gemini skills install <repo>` / `uninstall`.

### 2.5 Summary of roots

| Agent | User root(s) | Project root(s) | Reads `.agents/skills` | Symlinks | Picks up changes |
| --- | --- | --- | --- | --- | --- |
| Claude Code | `~/.claude/skills` | `.claude/skills` (+ nested, parents) | no | per-entry, documented (with regressions) | live watch |
| Codex | `~/.agents/skills` (+ deprecated `~/.codex/skills`), `/etc/codex/skills` | `.agents/skills` | yes (primary) | documented | restart recommended |
| Cursor | `~/.cursor/skills`, `~/.agents/skills` (+ `~/.claude`, `~/.codex`) | `.cursor/skills`, `.agents/skills` (+ legacy) | yes | not documented | n/a |
| Gemini CLI | `~/.gemini/skills`, `~/.agents/skills` | `.gemini/skills`, `.agents/skills` | yes | `/skills link` | not documented |

Claude Code is the notable holdout. It does not read `.agents/skills`, so any
cross-agent tool still has to write into `~/.claude/skills` separately.

---

## 3. Cross-agent distribution tools

### 3.1 `npx skills`: vercel-labs/skills (32.4k★)

Source: [repo](https://github.com/vercel-labs/skills), [`src/installer.ts`](https://raw.githubusercontent.com/vercel-labs/skills/main/src/installer.ts), [AGENTS.md](https://github.com/vercel-labs/skills/blob/main/AGENTS.md), [DeepWiki lock-file notes](https://deepwiki.com/vercel-labs/skills/5.9-skill-lock-file-system).

This is the de facto package manager for skills. Other projects publish their
install instructions against it. For example, agentmemory's README says
`npx skills add rohitg00/agentmemory -y -a '*'` installs into every detected agent.

- **Commands**: `add`, `list`, `find`, `remove`, `update`, `check`, `init`.
  `find` searches the [skills.sh](https://skills.sh) directory.
- **Targets**: 75+ agents, each with a project path and a global path. Examples:
  - Claude Code: `.claude/skills` / `~/.claude/skills`.
  - Codex: `.agents/skills` / `~/.codex/skills`.
  - Cursor: `.agents/skills` / `~/.cursor/skills`.
  - Gemini CLI: `.agents/skills` / `~/.gemini/skills`.
  - OpenCode: `.agents/skills` / `~/.config/opencode/skills`.
  - "Universal" agents (Amp, Cline, Codex) share `.agents/skills` / `~/.agents/skills`.
- **Repo discovery**: looks for a root `SKILL.md`, then in `skills/`,
  `skills/.curated|.experimental|.system/` and agent directories, to a depth of 3. A
  shallower `SKILL.md` shadows anything nested below it. `--full-depth` searches
  recursively. `metadata.internal: true` hides a skill unless
  `INSTALL_INTERNAL_SKILLS=1`.
- **Delivery (the part worth copying)**: in the default symlink mode, the skill is
  written once to a **canonical directory `.agents/skills/<name>`**. Each agent's
  directory then gets a **relative** symlink to it on Unix and a **junction** on
  Windows (`symlinkType = platform() === 'win32' ? 'junction' : undefined`). If the
  link cannot be created, the installer **falls back to copying**. If an agent's
  directory resolves to the canonical directory itself, no link is made
  (`realTarget === realLinkPath → return true`). `--copy` forces independent copies.
- **Lock files**: a global `~/.agents/.skill-lock.json` (schema v3) and a project
  `skills-lock.json` meant to be committed. The project lock is replayed by an
  `experimental_install` command. Each entry records its source and a
  `skillFolderHash`, which is the **GitHub tree SHA** of the skill folder.
- **Updates**: `check` sends the lock entries to a Vercel endpoint, which compares
  them against the latest tree SHAs. `update` reinstalls only the changed skills by
  re-running `add <tree-url> -g -y`. Nothing is pinned to a commit. "Update" means
  "latest on the default branch". Private repos get an empty `skillFolderHash`, so
  they always report "reinstall needed"
  ([#162](https://github.com/vercel-labs/skills/issues/162)).
- **Telemetry**: anonymous install telemetry, turned off with `DISABLE_TELEMETRY=1`
  or `DO_NOT_TRACK=1`. The same install counts rank the skills.sh leaderboard.

### 3.2 OpenSkills: numman-ali/openskills

Source: [repo](https://github.com/numman-ali/openskills).

OpenSkills took a different route to reach agents with no native skills support. It
installs into `./.claude/skills/` by default, into `./.agent/skills/` with
`--universal`, or into `~/.claude/skills/` with `--global`. Its lookup order is
`./.agent`, `~/.agent`, `./.claude`, `~/.claude`.

`openskills sync` then writes an `<available_skills>` XML block, in the same shape
as Claude Code's internal catalog, into **`AGENTS.md`**. The agent activates a skill
by running the shell command `npx openskills read <name>`, which prints the body.
This is the "simulated skills" pattern: the catalog goes into the always-loaded rules
file, and a CLI stands in for the activation tool. Progressive disclosure still works
for any agent that reads `AGENTS.md` and can run shell commands. The cost is that the
catalog now lives in a file the user also edits.

### 3.3 rulesync: dyoshikawa/rulesync

Source: [repo README](https://raw.githubusercontent.com/dyoshikawa/rulesync/main/README.md), [configuration](https://rulesync.dyoshikawa.com/guide/configuration), [CLI reference](https://rulesync.dyoshikawa.com/reference/cli-commands), [PR #2994](https://github.com/dyoshikawa/rulesync/pull/2994).

rulesync is a generator rather than a linker. Skills are authored once under
`.rulesync/skills/`. `rulesync generate --targets <tools> --features skills` then
writes each tool's native layout. For tools with no native skills, the
`simulateSkills` option emits a rule file that lists the skills, the same idea as
OpenSkills. `rulesync import` pulls existing tool configs back into `.rulesync/`.

**External skills are declarative.** They are listed under `sources` in
`rulesync.jsonc` and fetched into `.rulesync/skills/.curated/`. A **`rulesync.lock`**
records `requestedRef`, `resolvedRef`, `resolvedAt` and a per-skill integrity hash.
It is the only tool surveyed that pins a commit and stores a content hash in the same
lock file. A 2026 fix made rulesync re-fetch when the requested skill set grows past
what the lock covers. `global` mode targets user-scope files. (The GitHub star count
could not be read reliably. The page showed about 1.5k.)

### 3.4 cc-switch: farion1231/cc-switch (≈136k★, Chinese ecosystem)

Source: [repo](https://github.com/farion1231/cc-switch), [skills manual](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/en/3-extensions/3.3-skills.md).

cc-switch is a Tauri desktop app, with a CLI port at
[SaladDay/cc-switch-cli](https://github.com/saladday/cc-switch-cli). It manages
providers, MCP servers and skills for Claude Code, Codex, Gemini CLI, OpenCode,
OpenClaw, Hermes and others. Its skills design is the closest match to a vault-style
manager:

- **Single source of truth**: skill files live in `~/.cc-switch/skills/`, or
  `$CC_SWITCH_CONFIG_DIR/skills`. A setting can move the store to `~/.agents/skills`
  so other tools see it too. Install state and per-app enablement live in the
  app's SQLite database, not in the files.
- **Delivery**: per-app toggles fan the skill out to `~/.claude/skills`,
  `~/.codex/skills`, `~/.gemini/skills`, `~/.config/opencode/skills` and
  `~/.hermes/skills`. A global "Skill Sync Method" setting chooses symlink or copy.
- **Sources**: preset repos (Anthropic, ComposioHQ, community picks), custom GitHub
  repos given as owner/name/branch/subdirectory, ZIP import, and skills.sh registry
  search since v3.13.0.
- **Updates (v3.13.0+)**: SHA-256 content hashes of the installed skill are compared
  with the remote. The app shows per-card "update" buttons and an "Update All". The
  CLI has `skills check-updates` and `skills update <name>|--all`.
- **Uninstall is reversible**: before deleting from every app directory and the
  store, the skill is **backed up to `~/.cc-switch/skill-backups/`**. A restore list
  shows the backups by date.
- **Known edge**: some agents keep reading their own bundled skill directory instead
  of the fanned-out one. Hermes is an example
  ([#5250](https://github.com/farion1231/cc-switch/issues/5250)). Delivering into a
  directory does not guarantee the agent loads from it.
- A side project, [SkillBridge](https://github.com/cg689/SkillBridge), does only the
  junction/symlink part for tools cc-switch does not cover. That suggests fan-out is
  being split off as a separate utility.

### 3.5 Plugin-based frameworks: obra/superpowers (291k★), ClaudeKit (2.2k★)

Source: [superpowers](https://github.com/obra/superpowers), [claudekit-skills](https://github.com/mrgoonie/claudekit-skills).

Superpowers is a methodology packaged as skills: TDD, systematic debugging,
brainstorming, planning, worktrees, subagent-driven development and writing skills.
It is also the most-starred skills project. It does **not** fan out from a single
store. Instead it ships **one package per agent's own plugin or extension system**:

- Claude Code and Codex: their official plugin marketplaces.
- Cursor: `/add-plugin superpowers`.
- Gemini CLI: `gemini extensions install https://github.com/obra/superpowers`.
- Copilot CLI and Factory Droid: marketplace registration.
- OpenCode: manual steps.

A **SessionStart hook** injects a `using-superpowers` bootstrap, so the skills are
active from the first message. Otherwise the agent would have to discover them from
their descriptions. A `.version-bump.json` keeps version numbers in step across the
per-agent packages. Updates come through each host's plugin updater.

ClaudeKit (50+ skills in 13 categories) moved from git-clone-and-copy to a Claude
Code plugin marketplace, installed with
`/plugin marketplace add mrgoonie/claudekit-skills`, to get automatic updates. It
now marks the manual install as legacy.

The lesson from both projects is that once agents have plugin systems, skill authors
distribute through those systems. Plugins bring versioning, updates and hooks that a
bare skill folder lacks. The price is N separate installs and no shared store.

### 3.6 Large catalog: tonsofskills / claude-code-plugins-plus-skills (2.8k★)

Source: [repo](https://github.com/jeremylongshore/claude-code-plugins-plus-skills).

This catalog holds 434 plugins and about 2,900 marketplace-visible skills across 19
categories, with 386 npm packages. You install through the Claude Code marketplace
(`/plugin marketplace add jeremylongshore/claude-code-plugins`) or the `ccpi` CLI
(`ccpi install <pack>`).

It separates artifacts by **provenance class**:

- canonical first-party skills;
- generated per-harness adapters;
- first-party npm packages;
- **upstream mirrors, each carrying a `.source.json` that records where it came from**.

Admission is gated by validation against the standard, a written STANDARDS.md and a
security policy for submissions.

### 3.7 First-party account sync: claude.ai → Claude Code

Claude Code now pulls skills that are enabled on the user's claude.ai account into
`~/.claude/skills/synced/`. It checks about every 10 minutes and adds, updates or
removes skills without a restart ([docs](https://code.claude.com/docs/en/skills)).
Synced skills are treated as less trusted: `!` shell injection, `@` file references
and `${CLAUDE_*}` variables are rendered as literal text, and display text is
sanitised. The broader platform still says custom skills "do not sync across
surfaces": claude.ai, the API and Claude Code filesystem skills are managed
separately ([overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)).

### 3.8 Content repos that rely on the tools above

- **agentmemory** ([rohitg00/agentmemory](https://github.com/rohitg00/agentmemory), 28.8k★) ships 17 skills. It
  tells users to run `npx skills add ... -a '*'`, or to drop the folders into any
  agent's native directory ("the same format works everywhere"). Its MCP wiring is
  handled by a separate `agentmemory connect <agent>` command.
- **anthropics/skills** (177.9k★) is the reference collection. It doubles as a
  Claude Code marketplace (`/plugin marketplace add anthropics/skills`, then
  `document-skills@anthropic-agent-skills` / `example-skills@...`). Most skills are
  Apache-2.0. The docx/pdf/pptx/xlsx skills are **source-available, not open
  source**. The repo also hosts the spec and a template
  ([repo](https://github.com/anthropics/skills)).

---

## 4. Catalogs and discovery

| Catalog | Kind | Scale (2026-09) | How entries get in | Trust signal |
| --- | --- | --- | --- | --- |
| [skills.sh](https://skills.sh) | leaderboard for `npx skills` | top entries: `find-skills` 3.5M installs, `grill-me` 1.2M | CLI install telemetry | [audits page](https://skills.sh/audits) combining **Gen Agent Trust Hub, Socket and Snyk** verdicts (Safe / Low / Medium / Critical / Pending) |
| [SkillsMP](https://skillsmp.com) | crawler/search engine | "3,000,000+" skills | aggregated from GitHub repos | none published; free REST API (50/day anonymous, 500/day with a key) and an MCP server |
| ClawHub (OpenClaw) | open registry | 10,700+ skills by Feb 2026 | publish with a GitHub account older than one week | VirusTotal scan per upload (see §5) |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | curated list | 75.6k★, "1000+" skills, 11 categories | PR | editorial |
| [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) | curated list | 15.2k★ | PR | editorial + a security section |
| tonsofskills | marketplace | ~2,900 skills | PR + spec validation | provenance classes, standards doc |
| anthropics/skills, openai/skills | vendor collections | 177.9k★ / 27.6k★ | vendor | vendor |

**Which discovery ecosystems work, and why.**

- **Catalogs tied to an install command get used.** skills.sh ranks what
  `npx skills` actually installs, so its ordering reflects real use and one command
  goes from finding a skill to having it. The awesome lists earn stars but hand the
  user a URL to paste somewhere.
- **Raw crawl size is not discovery.** SkillsMP's millions of indexed folders
  include forks, copies and dead repos. It offers no quality or safety signal, so
  the number mostly shows how cheap the format is to copy.
- **Open publishing plus sudden popularity invites attack.** ClawHub was open to
  any week-old GitHub account while OpenClaw's user base grew fast. It became the
  first mass-poisoning case (§5). The fixes it added afterwards were reactive: scan
  on upload, auto-hide after three user reports.
- **Vendor collections set the format but are moving into plugins.** Both
  anthropics/skills and openai/skills are being consumed as plugin marketplaces, and
  openai/skills is deprecated in favour of the Plugins repo. The long-term channel
  looks like each agent's plugin marketplace, with skills.sh-style indexes on top
  for skills that are not packaged as plugins.

---

## 5. Security: threats, incidents, scanners

### 5.1 Why skills are an attack surface

A skill is instructions plus code, loaded into an agent that already has shell,
file and network access. Anthropic's own guidance is to use skills "only from
trusted sources" and to "treat [them] like installing software". It warns that
skills which fetch external URLs can change behaviour after install, and that
Claude Code skills have full network access. Claude Enterprise can turn on **skill
content scanning** for skills uploaded in claude.ai and Cowork. That scanning does
not cover the API or Console
([overview, security considerations](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)).

Reversec's "Skill Issues" (5 May 2026) shows how to get code execution through
`allowed-tools` frontmatter and agent permission overrides
([post](https://labs.reversec.com/posts/2026/05/skill-issues-compromising-claude-code-with-malicious-skills-agents-part-1)).
This matters because in Claude Code `allowed-tools` pre-approves tools without
restricting others (§2.1).

### 5.2 Incidents and measurements

- **ClawHavoc (ClawHub, Jan–Feb 2026).**
  - The first malicious skill appeared on 27 Jan, with a surge on 31 Jan. Koi
    Security disclosed the campaign on 1 Feb after auditing 2,857 skills: 341 were
    malicious, and 335 of them used a fake **"Prerequisites"** section. On macOS it
    told the user or agent to paste an obfuscated script from glot.io, which fetched
    **Atomic macOS Stealer**. On Windows it pointed to an `openclaw-agent.zip`
    containing a trojan.
  - The lures were crypto wallets, Polymarket bots, YouTube tools, auto-updaters and
    ClawHub typosquats. Some skills hid reverse shells in working code or sent bot
    credentials to webhook.site.
  - As the registry grew past 10,700 skills, the count reached 824. Antiy CERT later
    attributed 1,184 packages to 12 author IDs.
  - Response: skills with more than three unique reports are auto-hidden. From
    7 Feb 2026, every upload is scanned by VirusTotal: the bundle's SHA-256 is looked
    up, unknown bundles are uploaded to **Code Insight**, "benign" skills are approved
    automatically and "suspicious" ones get a warning.
  - Sources: [The Hacker News](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html), [VirusTotal integration](https://thehackernews.com/2026/02/openclaw-integrates-virustotal-scanning.html), [OpenClaw blog](https://openclaw.ai/blog/virustotal-partnership), [Antiy](https://www.antiy.net/p/clawhavoc-analysis-of-large-scale-poisoning-campaign-targeting-the-openclaw-skill-market-for-ai-agents/), [Unit 42](https://unit42.paloaltonetworks.com/openclaw-ai-supply-chain-risk/).
- **ToxicSkills (Snyk, 5 Feb 2026).** Snyk scanned 3,984 skills from ClawHub and
  skills.sh.
  - 13.4% (534) had at least one critical issue; 36.82% (1,467) had at least one flaw.
  - 76 payloads were confirmed malicious, and 8 were still live at publication.
  - Every confirmed malicious skill contained malicious code, and **91% combined it
    with prompt injection**, using obfuscation and Unicode smuggling.
  - 10.9% of ClawHub skills contained hard-coded secrets.
  - Some samples were delivered inside password-protected ZIPs to get past scanners.
  - Source: [Snyk](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/).
- **Scanner blind spot: test files (Gecko Security, May 2026).** A payload in a
  bundled `*.test.ts`, `*.spec.js` or `conftest.py` inside `.agents/skills/` passed
  **Snyk Agent Scan, Cisco's scanner and VirusTotal Code Insight**. None of them
  treats test files as something that executes, but the project's test runner picks
  them up through its globs and runs them with full access to the environment, files
  and SSH keys, without the agent being involved. Gecko's recommendations:
  - exclude `.agents/` from test-runner globs;
  - block merges that add test files under skill directories;
  - pin skill sources to commit hashes;
  - make scanner vendors say which files they actually analyse.
  - Source: [VentureBeat](https://venturebeat.com/security/anthropic-skill-scanners-passed-every-check-malicious-code-test-file).

### 5.3 OWASP Agentic Skills Top 10 (incubator, v1.0-2026)

Source: [project site](https://owasp.github.io/www-project-agentic-skills-top-10/), [OWASP page](https://owasp.org/www-project-agentic-skills-top-10/).

| ID | Risk |
| --- | --- |
| AST01 | Malicious skills |
| AST02 | Supply-chain compromise (hijacked repos and dependencies) |
| AST03 | Over-privileged skills |
| AST04 | Insecure metadata (unsafe manifest parsing that executes code at install) |
| AST05 | Untrusted external instructions (behaviour fetched from URLs at runtime) |
| AST06 | Weak isolation (host-level execution) |
| AST07 | **Update drift** (unpinned versions auto-update to malicious patches) |
| AST08 | Poor scanning (pattern matching beaten by natural-language payloads) |
| AST09 | No governance (no inventory, approval or audit trail) |
| AST10 | Cross-platform reuse (ported skills lose their security metadata) |

Its mitigations:

- sign published skills and carry a `content_hash` in the manifest (Merkle-root signing);
- declare minimal permissions in an explicit manifest;
- pin nested dependencies to immutable hashes;
- scan behaviour at both publish and install time;
- sandbox by default;
- deny writes to identity files such as `AGENTS.md` and `MEMORY.md` by default.

AST10 applies directly to fan-out. Claude Code-only fields such as `allowed-tools`,
`hooks` and `disable-model-invocation`, and Codex's `agents/openai.yaml`, are dropped
or ignored when the same folder is loaded by another agent.

### 5.4 Scanners

- **Snyk Agent Scan** ([snyk/agent-scan](https://github.com/snyk/agent-scan), 3.1k★;
  formerly Invariant Labs' `mcp-scan`).
  - Discovers MCP configs and skills for Claude Code/Desktop, Cursor, VS Code,
    Copilot, Windsurf, Gemini CLI and others, across system, user, project and
    extension scopes.
  - Sends sanitised component metadata, with secrets redacted, to Snyk's analysis
    API, so a `SNYK_TOKEN` is required.
  - Detects prompt injection, tool poisoning or shadowing, toxic flows, malware
    payloads, hard-coded secrets and, from 0.6, 14 risk indicators.
  - Can start stdio MCP servers during a scan, so it asks for consent per server.
- **Cisco AI Defense skill-scanner**
  ([cisco-ai-defense/skill-scanner](https://github.com/cisco-ai-defense/skill-scanner),
  2.5k★, Apache-2.0, `pip install cisco-ai-skill-scanner`).
  - Layers: static YAML and YARA-X rules → Python AST/dataflow behavioural analysis
    → an optional LLM judge (Claude or OpenAI) → a meta-analyzer that filters false
    positives → optional VirusTotal and AI Defense cloud checks.
  - Outputs JSON, SARIF, HTML and Markdown. Ships a GitHub Action and a pre-commit hook.
  - Its README states: "No findings ≠ no risk."
- **Registry-side scanning.** ClawHub uses VirusTotal Code Insight at upload.
  skills.sh shows combined Gen/Socket/Snyk audit verdicts. Claude Enterprise scans
  skill content uploaded to claude.ai.

Across all three approaches, pattern and LLM scanning is advisory. Every vendor
disclaims completeness, and the test-file bypass shows each scanner's idea of what
"executes" is narrower than what a developer's toolchain actually runs.

---

## 6. Comparison

| | Store model | Fan-out | Link method | Update signal | Pinning | Integrity | Safety at install |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `npx skills` | canonical `.agents/skills` | 75+ agents | relative symlink / Windows junction, copy fallback | GitHub tree SHA via hosted check | no (latest) | tree SHA in lock | audit badges on skills.sh only |
| OpenSkills | `.claude` / `.agent` dir | via `AGENTS.md` catalog + `read` CLI | n/a (simulated) | `update` re-pulls | no | none | none |
| rulesync | `.rulesync/skills` (generated out) | many tools, simulated where missing | generate/copy | re-fetch | `resolvedRef` | per-skill integrity hash | none |
| cc-switch | `~/.cc-switch/skills` + SQLite state | 5–7 desktop agents | user-selected symlink or copy | SHA-256 vs remote | no | content hash | backup before uninstall |
| Superpowers / ClaudeKit | one plugin per host | per-host plugin | host plugin cache | host updater | host-defined | host-defined | none beyond host |
| claude.ai sync | account | Claude Code only | download to `synced/` | 10-min poll | n/a | n/a | shell/`@`/vars neutralised |
| Codex `$skill-installer` | `.agents/skills` | Codex only | copy | none | no | none | none |
| Gemini CLI | native dirs | Gemini only | `link` / install | none | no | none | **consent prompt on activation** |

---

## 7. Patterns and trade-offs

- **The format has settled; the location is still settling.** Everyone speaks
  `SKILL.md` + frontmatter + progressive disclosure. `.agents/skills` is becoming the
  shared root (Codex primary, Cursor, Gemini CLI and OpenCode all read it), but
  Claude Code only reads `.claude/skills`. So fan-out is still needed. It may shrink
  to "`.agents/skills` + Claude" as more agents converge.
- **One canonical copy plus links is the common delivery model.** `npx skills` and
  cc-switch both keep one store and link it into each agent. Relative symlinks on
  Unix, junctions on Windows and copy as the fallback is the tested combination.
  Symlinks keep one source of truth and make updates instant. Copies survive agents
  that mishandle links (Claude Code has had several regressions, and Codex's
  discovery has broken outright) and resist in-place tampering. Offering both, per
  install, is the norm.
- **Delivery ≠ loading.** Agents may cache, need a restart (Codex), skip symlinked
  roots after a security patch (Claude Code), or keep reading their own bundled
  directory (Hermes). A manager that writes a directory and reports success can be
  wrong about what the agent actually sees.
- **Two ways to reach agents without native skills.** One is the simulated catalog:
  write an `<available_skills>` block into `AGENTS.md` and give the agent a
  shell-command reader (OpenSkills, rulesync). The other is to target the agent's
  plugin or extension system (Superpowers). The first keeps one store. The second
  gets hooks and updates but means N installs.
- **Plugins are absorbing distribution.** Cursor accepts remote skills only inside
  plugins. Codex's skills catalog is deprecated for plugins. The Claude Code
  marketplace is where the largest collections live. Bare skill folders remain the
  format, while plugins are the package.
- **Update detection splits by whether there is a hash to compare.** Tools that
  record a content or tree hash (skills CLI, cc-switch, rulesync) can say "changed
  upstream". Tools without one can only re-pull. Few pin. rulesync's
  requested-vs-resolved ref is the exception, and OWASP lists unpinned auto-update
  (AST07) as a top-10 risk.
- **Budgets are real and differ per agent.** Claude Code: 1,536 chars per
  description, about 1% of context for the listing, least-used descriptions dropped
  first. Codex: 2% of context or 8,000 chars. Overflowing drops descriptions without
  any error. A large skill library delivered to every agent degrades triggering for
  all of them.
- **Security is layered, and no layer is sufficient.** Registry scanning,
  install-time scanning and agent-side controls all exist. The agent-side controls
  are Gemini's consent prompt, Claude Code's neutralised synced skills and
  `disableSkillShellExecution`, and the standard's advice to trust-gate project
  skills. Every scanner
  vendor disclaims completeness, and real attacks used plain-English "prerequisites"
  and files outside what the scanners analyse.

## 8. Worth borrowing / worth avoiding

**Worth borrowing**

- A single canonical store with **relative symlinks, Windows junctions and an
  automatic copy fallback**. Skip linking when the agent's directory already is
  the store (`npx skills`).
- Linking **each skill entry**, never replacing an agent's whole `skills/`
  directory. That is the case Claude Code documents as supported. Directory-level
  symlinks are the ones that regressed.
- Keeping **enablement state outside the skill files** (cc-switch's database). The
  folder stays a pure, portable standard skill.
- **Backup-before-uninstall** with a restore list (cc-switch). It is a cheap undo
  for a destructive fan-out delete.
- A **lock record with source, requested ref, resolved ref and content hash**
  (rulesync, plus the skills CLI's tree SHA). Together they make "update available",
  reproducible reinstall and tamper detection possible from one record.
- A **provenance file** on anything mirrored from upstream (tonsofskills'
  `.source.json`). It shows where a skill came from after it has been copied.
- **Lenient parsing with diagnostics**, as the standard's client guide recommends:
  load on cosmetic violations and show them to the user. Strict rejection breaks
  skills written for other clients.
- **Treating the per-agent budget as a delivery constraint.** Warn when the
  combined description size of what is delivered to an agent exceeds that agent's
  listing budget, rather than letting the agent silently drop text.
- Showing a skill's **powers before enabling it**: `allowed-tools`, `hooks`, shell
  injection, bundled executables, test files. Gemini's consent prompt and Claude
  Code's handling of synced skills do this at load time. A manager can show the same
  facts earlier.
- **Scanning with honest labelling**: layered checks (static rules, then
  behavioural analysis, then an optional LLM judge), SARIF output, and an explicit
  "no findings ≠ safe". Cover every file in the bundle, including tests and
  archives.

**Worth avoiding**

- **Update means latest.** Re-pulling the default branch on update (the
  skills CLI's model) is exactly OWASP AST07 (update drift). Updates should show
  what changed and apply only on request.
- **Open publishing with trust decided after the fact** (ClawHub). Auto-hide after
  three reports and after-the-fact scanning came only once hundreds of malware
  skills were live.
- **Treating `allowed-tools` as a sandbox.** In Claude Code it only pre-approves
  tools and restricts nothing, and other agents may ignore it. Delivering it
  unchanged across agents both widens permissions where it is honoured and silently
  drops them where it is not (AST10).
- **Assuming the agent's own format extensions carry over.** Claude Code's `hooks`,
  `context: fork` and `!` injection and Codex's `agents/openai.yaml` mean different
  things, or nothing, in other agents. A cross-agent manager should report which
  fields each target will ignore.
- **Leaderboards without safety signals, or crawls without curation** (SkillsMP).
  Size alone tells the user nothing and gives malicious skills more places to hide.
- **Reporting "delivered" from the filesystem alone.** Several agents have shipped
  discovery regressions. Confirm what the agent actually lists where possible, for
  example via its list command or skill-doctor output.
