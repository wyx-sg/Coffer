# Agent plugin management: how other products do it

**Feature**: seeing, and managing (enable / disable / uninstall, not installing), the plugins and extensions installed in a coding agent from outside that agent · **Coffer spec**: [agent-registry](../../openspec/specs/agent-registry/spec.md) (plugin facet) · **Related ADRs**: [writing-agent-native-config-safely](../decisions/writing-agent-native-config-safely.md), [agent-descriptor-manifest](../decisions/agent-descriptor-manifest.md)
**Researched**: 2026-09 · **Method**: web research, primary sources (official docs, source repos, issue trackers), plus direct inspection of a real install of Claude Code 2.1.281 and Codex CLI 0.155.1 on macOS

---

## Scope and vocabulary

"Plugin" names three different things across coding agents, and the difference decides what an outside tool can safely do:

| Model | What a plugin is | Agents |
| --- | --- | --- |
| **Bundle of components** | A directory with a manifest that bundles skills, subagents, hooks, MCP servers, commands, LSP servers; distributed through git-hosted *marketplaces* | Claude Code, Codex, Cursor (2.5+), Gemini CLI extensions, GitHub Copilot / VS Code (via Agent Plugins) |
| **Editor extension (VSIX)** | A packaged JS extension for the VS Code extension host, from a central registry | VS Code, Cursor, Windsurf / Devin Desktop, Positron, VSCodium |
| **Code module** | A JS/TS module the agent imports and calls with a context object; hooks are functions | OpenCode |

A fourth model, **config blocks** (Continue), is a plugin system only in name: a "block" is a fragment of the user's config file.

For every product below the note answers the same five questions: where the *install state* lives, where the *enabled state* lives, what the *documented write surface* is, what the agent's *own CLI/API* offers for enable / disable / uninstall, and what happens when things go wrong.

---

## 1. Claude Code plugins

Claude Code (Anthropic) has the most elaborate plugin system of any coding agent and the most documented split between user-facing config and internal state. Sources: [Plugins reference](https://code.claude.com/docs/en/plugins-reference), [Discover and install plugins](https://code.claude.com/docs/en/discover-plugins), [Plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), [Settings reference](https://code.claude.com/docs/en/settings-reference) — all checked 2026-09-24 against Claude Code 2.1.281.

### 1.1 The package: `.claude-plugin/plugin.json`

A plugin is a directory. The manifest at `.claude-plugin/plugin.json` is *optional*; when present only `name` (kebab-case) is required. Metadata fields: `displayName`, `version`, `description`, `author{name,email,url}`, `homepage`, `repository`, `license`, `keywords`, `metadata`, `defaultEnabled`. Components are found by **fixed directory convention at the plugin root** (never inside `.claude-plugin/`), overridable by path fields in the manifest ([reference](https://code.claude.com/docs/en/plugins-reference)):

| Component | Default location | Manifest override | Override semantics |
| --- | --- | --- | --- |
| Skills (slash commands) | `skills/<name>/SKILL.md`, root `SKILL.md` | `skills` | *adds to* `skills/` |
| Flat commands (legacy) | `commands/*.md` | `commands` | replaces |
| Subagents | `agents/*.md` (nested dirs become `plugin:folder:agent`) | `agents` | replaces |
| Hooks | `hooks/hooks.json` or inline | `hooks` | merged |
| MCP servers | `.mcp.json` or inline | `mcpServers` | merged |
| LSP servers | `.lsp.json` or inline | `lspServers` | merged |
| Output styles, workflows | `output-styles/`, `workflows/` | `outputStyles`, `workflows` | replaces |
| Themes, monitors, evals (experimental) | `themes/`, `monitors/monitors.json`, `evals/` | `experimental.*` | replaces |
| Executables | `bin/` (added to `PATH`) | — | — |
| Default settings | `settings.json` | — | — |

Further manifest features that matter for a manager:

- **`userConfig`** — typed prompts (`string`, `number`, `boolean`, `directory`, `file`, with `sensitive`, `required`, `options`, `default`) collected at install; substituted as `${user_config.KEY}` in skill/agent content and exported as `CLAUDE_PLUGIN_OPTION_<KEY>` to hooks. Values supplied from a project's `.claude/settings.json` are ignored, because a cloned repo could otherwise inject them into hook commands.
- **`dependencies`** — other plugins by name, optionally with a semver range; dependencies are auto-installed and auto-enabled with the dependent, and `claude plugin prune` (alias `autoremove`) removes orphaned auto-installed ones.
- **Path variables** — `${CLAUDE_PLUGIN_ROOT}` (the install directory, which *changes on every update*), `${CLAUDE_PLUGIN_DATA}` (= `~/.claude/plugins/data/<id>/`, survives updates), `${CLAUDE_PROJECT_DIR}`.
- **Security carve-outs** — plugin subagents may not declare `hooks`, `mcpServers` or `permissionMode`; `../` escapes out of the plugin root are rejected; Node dependencies are installed with `npm ci --ignore-scripts` / `bun install --frozen-lockfile --ignore-scripts` (no lifecycle scripts, 60 s timeout).

### 1.2 Marketplaces: `.claude-plugin/marketplace.json`

Plugins are installed *from a marketplace*: a catalog file at `.claude-plugin/marketplace.json` in a repo or URL, with required `name`, `owner{name}` and `plugins[]` ([marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)). Each entry has a `name` and a `source`:

- relative path (`"./plugins/x"`), `github` (`repo`), git `url`, `git-subdir` (`url` + `path`), `npm` (`package`), HTTPS `archive` (zip), and `command` (an external tool writes the plugin).
- `strict: true` (default) makes the plugin's own `plugin.json` authoritative with the marketplace entry supplementing it; `strict: false` makes the marketplace entry the whole definition.
- Version: without `version`, the resolved commit SHA (git) or archive digest is the version; with `version`, users only receive an update when the string changes.
- `defaultEnabled: false` on the entry installs the plugin disabled; the entry value beats the manifest value.
- `renames` — an append-only map `old-name → new-name | null`. On startup Claude Code (2.1.193+) rewrites the old key in the user's settings, or drops it with a "removed from the marketplace" notice for `null`. Older versions report `plugin-not-found`.
- Reserved names (e.g. `claude-code-marketplace`, `anthropic-plugins`, `agent-skills`, and since 2.1.275 `npm`, `pip`, `github`, `gh`) cannot be claimed by third parties — an anti-impersonation measure.

The official catalog is [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official). Marketplaces are git-cloned to `~/.claude/plugins/marketplaces/<name>/` and refreshed in the background; private repos use the user's existing git credential helpers, never an interactive prompt.

### 1.3 Where state lives

Three distinct layers, only one of which is documented as user-editable config:

**(a) Enabled state — `enabledPlugins` in the settings files (the documented write surface).** An object `"<plugin>@<marketplace>": true|false` that may appear in every settings scope ([settings reference](https://code.claude.com/docs/en/settings-reference)):

| Scope | File | Notes |
| --- | --- | --- |
| user | `~/.claude/settings.json` | default for `claude plugin install` |
| project | `.claude/settings.json` | committed; team-shared |
| local | `.claude/settings.local.json` | per-machine, gitignored |
| managed | managed settings (file / MDM / server) | read-only to users |

Precedence is the documented part managers most often get wrong: **project beats user**, so `false` in `~/.claude/settings.json` does *not* disable a plugin the repo's `.claude/settings.json` enables; the documented opt-out is `false` in `.claude/settings.local.json`; **managed beats everything** — a managed `false` blocks installation at every scope and hides the plugin, and a managed `true` cannot be turned off. A plugin with no entry anywhere falls back to its `defaultEnabled`. The third-party TUI ccpm (below) encodes this as "Local > Project > User". Enabling a plugin from an external source in a project file does *not* install it for teammates; each user still has to install it.

**(b) Install records — `~/.claude/plugins/installed_plugins.json` and `known_marketplaces.json` (internal, undocumented format).** Observed on 2.1.281 (`"version": 2`): `plugins` maps each `name@marketplace` id to an *array* of installations, each with `scope`, `installPath`, `version`, `installedAt`, `lastUpdated`, optional `gitCommitSha`, and `projectPath` for project/local-scope installs. `known_marketplaces.json` maps marketplace name to `{source, installLocation, lastUpdated}`. Neither file is described in the reference docs; they surface only in the seed-directory section, which describes `known_marketplaces.json` + `marketplaces/<name>/` + `cache/<marketplace>/<plugin>/<version>/` as "the structure of `~/.claude/plugins`" ([marketplaces: seed directory](https://code.claude.com/docs/en/plugin-marketplaces)). Also observed in the same directory: `blocklist.json` (a fetched list of `{plugin, added_at, reason, text}` entries — a server-pushed kill list, undocumented), `plugin-catalog-cache.json` (catalog with per-plugin token-cost estimates), `data/`, `synced/`.

**(c) Code — the versioned cache.** Marketplace plugins are *copied* to `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. On update or uninstall the old version directory is marked orphaned and swept "roughly 14 days later", so already-running sessions keep working; Glob/Grep skip orphaned directories ([reference: plugin caching](https://code.claude.com/docs/en/plugins-reference)). Persistent plugin state goes to `~/.claude/plugins/data/<id>/`, which `uninstall` deletes unless `--keep-data`. Two further sources load *without* an install record: **skills-dir plugins** (any `~/.claude/skills/<x>/.claude-plugin/plugin.json` loads as `<x>@skills-dir`, in place) and **synced plugins** from the user's claude.ai account (`~/.claude/plugins/synced/`, id `<name>@synced`; opt out with `syncClaudeAiPlugins: false`, which also moves them to `~/.claude/plugins/.trash/`).

The consequence for an outside tool: the *list* of plugins is the union of install records, skills-dir folders and synced folders, each joined with the merged `enabledPlugins` view; the *only* layer meant to be edited is (a).

### 1.4 The agent's own management surface

`claude plugin` (checked with `--help` on 2.1.281):

| Command | Relevant flags | Writes |
| --- | --- | --- |
| `list` | `--json`, `--available` (with `--json`) | nothing; JSON rows carry `id`, `version`, `scope`, `enabled`, `installPath`, `installedAt`, `lastUpdated` |
| `details <name>` | | nothing; component inventory + projected token cost |
| `enable <plugin>` / `disable [plugin]` | `-s/--scope user\|project\|local` (default auto-detect), `-a/--all`, `--json` | `enabledPlugins` in the scope's settings file |
| `uninstall <plugin>` (alias `remove`) | `-s/--scope` (default `user`), `--keep-data`, `--prune`, `-y`, `--json` | settings + install records + data dir; cache orphaned |
| `install`, `update`, `prune`, `marketplace add\|list\|remove\|update`, `validate`, `init`, `tag`, `eval` | | — |

`--json` on enable/disable/uninstall prints "one machine-readable result line on stdout … (same exit codes)", which makes the CLI a practical delegation target for a manager. Inside a session, `/plugin` opens a TUI whose **Installed** tab groups by scope, sorts load errors and unresolved dependencies first, folds disabled plugins at the bottom, shows a **Not used recently** group (unused ≥ 2 weeks over ≥ 10 sessions) and a per-plugin **Last used** line, and a detail view listing the plugin's commands, skills, agents, hooks, MCP and LSP servers ([discover-plugins](https://code.claude.com/docs/en/discover-plugins)).

Uninstalling a plugin that the *project* file enables asks which scope is meant: disable for me (writes a `false` override to `.claude/settings.local.json`, leaves the project install) or uninstall for everyone (edits the shared `.claude/settings.json`).

Changes do not always apply live: enabling/disabling mid-session can invalidate the prompt cache, so Claude Code may defer activation to `/reload-plugins` (or `--force`); the shell `claude plugin` commands only take effect for the next session or reload.

### 1.5 Team and managed distribution

- `extraKnownMarketplaces` in a repo's `.claude/settings.json` auto-registers a marketplace for teammates — but only after they accept the workspace-trust dialog; untrusted folders (including `-p` runs) ignore it silently.
- Managed-only keys: `strictKnownMarketplaces` (allowlist of marketplace sources, enforced before any network or disk access on add/install/update/refresh/auto-update; an empty array is total lockdown, including Anthropic's marketplace), `blockedMarketplaces` (denylist, with `owner/*` wildcards since 2.1.223 — before that the wildcard silently matched nothing).
- Team/Enterprise orgs can register a private marketplace in the claude.ai admin console; `CLAUDE_CODE_PLUGIN_SEED_DIR` pre-bakes a read-only plugin tree into container images (seed entries overwrite user entries every start; auto-update off).

### 1.6 Failure modes worth knowing

- **Silent drop of local-only `enabledPlugins`.** If `enabledPlugins` exists only in `settings.local.json` and not in `settings.json`, the merge discards it: no error, the `/plugin` tabs contradict each other, and (per a later comment) skills still load while hooks never fire. Filed as [#25086](https://github.com/anthropics/claude-code/issues/25086) (closed as duplicate) and re-filed as [#27247](https://github.com/anthropics/claude-code/issues/27247), which the stale-bot closed as *not planned* on 2026-04-14 without a fix being referenced. Whether current versions still reproduce it was not verified; a writer that always keeps an `enabledPlugins` object present in the base file is immune either way.
- **Install not recorded at project scope** — [#15524](https://github.com/anthropics/claude-code/issues/15524): `install` did not update the project `settings.json` (closed as duplicate).
- **`CLAUDE_PLUGIN_ROOT` moves on update**; anything that caches a plugin's path (including a manager's own index) goes stale after an update and must re-read the install records.
- **Plugin4Shell** (see §9): SHA-pinned git sources could be redirected to attacker commits before 2.1.179.

---

## 2. Codex plugins

OpenAI's Codex gained a plugin system in 2026 that is shared with ChatGPT ("a universal plugin directory shared between both products"). Sources: [Plugins](https://learn.chatgpt.com/docs/plugins), [Build plugins](https://developers.openai.com/plugins/build/plugins), [Enterprise plugin management](https://learn.chatgpt.com/docs/enterprise/plugin-management), [Config reference](https://learn.chatgpt.com/docs/config-file/config-reference) (the `developers.openai.com/codex/*` URLs now 308-redirect to `learn.chatgpt.com/docs/*`), the [openai/codex](https://github.com/openai/codex) source, and a local Codex CLI 0.155.1 install — checked 2026-09-24.

### 2.1 The package

Components: **skills**, **MCP servers**, **apps** (connector mappings in `.app.json`), **hooks**, and presentation assets. Two manifest layouts coexist:

- The **portable** layout — a root `plugin.json` conforming to Agent Plugins 1.0 (§3), with `skills/`, `mcp.json`, `hooks/`, `assets/`; OpenAI-specific data goes under `extensions."com.openai"` (`apps`, `hooks`, `interface`).
- The **compatibility overlay** `.codex-plugin/plugin.json`, used as a fallback when the root manifest has no `com.openai` extension. Every plugin cached on the inspected machine used this form, with keys such as `name`, `version`, `skills: "./skills/"`, `apps: "./.app.json"`, `interface{displayName, shortDescription, category, capabilities, brandColor, logo, screenshots, defaultPrompt, …}`, and inline `hooks` (e.g. `Stop`/`SubagentStop` hooks of type `mcp_tool`).

All manifest paths must be relative, start with `./`, and stay inside the plugin root ([build plugins](https://developers.openai.com/plugins/build/plugins)).

### 2.2 Marketplaces

A marketplace is a `marketplace.json` at `$REPO_ROOT/.agents/plugins/marketplace.json` (repo-scoped) or `~/.agents/plugins/marketplace.json` (personal); `$REPO_ROOT/.claude-plugin/marketplace.json` is read as a **legacy-compatible** format, so Claude Code marketplaces work unmodified. Entries carry `name`, `source{source: local|url|git-subdir|npm, …}`, `category`, and a **policy** block: `installation` ∈ `AVAILABLE | INSTALLED_BY_DEFAULT | NOT_AVAILABLE`, `authentication` ∈ `ON_INSTALL | on first use`.

Configured (non-default) marketplaces are recorded in `config.toml` (observed):

```toml
[marketplaces.shopee-be-harness]
source_type = "git"            # or "local"
source = "https://…/de-workspace.git"
ref = "release"
last_updated = "2026-09-09T15:11:21Z"
last_revision = "653dd666…"
```

Documented keys are `marketplaces.<name>.source`, `.source_type`, `.ref`, `.sparse_paths` ([config reference](https://learn.chatgpt.com/docs/config-file/config-reference)); `last_updated` / `last_revision` are written by Codex itself. Built-in marketplaces observed: `openai-bundled`, `openai-curated`, `openai-curated-remote`, `openai-primary-runtime`, `chatgpt-global`.

### 2.3 Where state lives

Unlike Claude Code, **enabled state and install presence share one file**, the user's `~/.codex/config.toml`:

```toml
[plugins."documents@openai-primary-runtime"]
enabled = true
```

`plugins.<id>.enabled` is documented as "Enable or disable a local-marketplace plugin using a `plugin-name@marketplace-name` key". Finer-grained, per-bundled-MCP-server keys also live here and are unique to Codex: `plugins.<id>.mcp_servers.<server>.enabled`, `.enabled_tools`, `.disabled_tools`, `.default_tools_approval_mode` (`auto|prompt|writes|approve`) and `.tools.<tool>.approval_mode` — so a user can keep a plugin but switch off or gate one of its MCP servers "without changing the plugin manifest" ([config reference](https://learn.chatgpt.com/docs/config-file/config-reference)).

Code is cached at `~/.codex/plugins/cache/$MARKETPLACE/$PLUGIN/$VERSION/` (`$VERSION` = `local` for local plugins). The whole feature is gated by the `plugins` feature flag (`codex features list` shows `plugins stable true`, plus `remote_plugin`, `plugin_sharing`, `recommended_plugins`); `--disable plugins` or `-c features.plugins=false` turns it off per run.

### 2.4 The agent's own management surface

`codex plugin` on 0.155.1:

| Command | Does |
| --- | --- |
| `list [--json] [--available]` | lists plugins per marketplace with status (`installed, enabled`, `not installed`, …), version, source |
| `add <plugin[@marketplace]>` | install |
| `remove <PLUGIN[@MARKETPLACE]>` (or `--marketplace`) | "Uninstall a plugin and remove its local cache" |
| `marketplace add\|list\|upgrade\|remove` | manage sources (`add owner/repo --ref main --sparse .agents/plugins`) |

There is **no `enable`/`disable` verb**; toggling is the `/plugins` browser in the TUI ("groups plugins by marketplace … install, uninstall, and toggle") or a direct edit of `plugins.<id>.enabled`. For programmatic clients the **app-server JSON-RPC** protocol exposes `plugin/list`, `plugin/installed`, `plugin/read`, `plugin/install`, `plugin/uninstall`, `plugin/reconcile`, `plugin/skill/read`, `marketplace/add|remove|upgrade`, and generic `config/value/write` / `config/batchWrite` ([protocol/common.rs](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/common.rs)); 0.156.0 (2026-09-22) added "Expose disabled plugin settings in the app-server API" and "Honor canonical plugin disables for shared connectors" ([release notes](https://github.com/openai/codex/releases/tag/rust-v0.156.0)). Uninstall removes the bundle but, per the docs, "separately connected MCP server integrations remain until manually disconnected".

### 2.5 Enterprise

Workspace admins import GitHub marketplaces (Codex or Claude format) under **Admin > Plugins**, synced daily, and apply per-role policies *Available / Installed (force) / Not Available*; any imported plugin declaring MCP servers is marked **Desktop only** ([enterprise plugin management](https://learn.chatgpt.com/docs/enterprise/plugin-management)). Managed `config.toml` (cloud or system) can predefine marketplace sources and defaults.

---

## 3. The cross-vendor format: Agent Plugins 1.0

Published 2026-08-06 by AWS, Anysphere (Cursor), Microsoft, OpenAI and Vercel, with Google joining as maintainer ([spec repo](https://github.com/agentplugins/agent-plugins-spec), ~1.3k stars as of 2026-09; [Vercel announcement](https://vercel.com/blog/introducing-agent-plugins); [GitHub changelog](https://github.blog/changelog/2026-08-12-agent-plugins-1-0-in-vs-code-copilot-cli-and-the-copilot-app/)). ChatGPT, Codex, Cursor, GitHub Copilot, Kiro and VS Code load it; Claude Code is not a launch client and keeps its own layout.

What the [1.0.0 spec](https://github.com/agentplugins/agent-plugins-spec/blob/main/spec/1.0.0.md) standardises is deliberately small: a root `plugin.json` with a **closed** schema (`$schema`, `name`, `version`, `description`, `author`, `homepage`, `repository`, `license`, `keywords`, `extensions`; unknown fields reported and ignored), exactly two component types — `skills/<x>/SKILL.md` (no deeper recursion) and a root `mcp.json` (never inline) — client-specific data under reverse-domain `extensions` keys or top-level directories, and `PLUGIN_ROOT` / `PLUGIN_DATA` env vars with a single non-recursive placeholder expansion. It explicitly chooses "filesystem directories as the package unit rather than archive formats … or registry-fetched bundles".

Everything a *manager* cares about is outside the spec: installation, enabled state, scopes, marketplaces, and provenance. The repo's `FUTURE_CONSIDERATIONS.md` lists permission UX, provenance verification, secret handling, enterprise controls, audit trails and dependency resolution as open. So even with a shared package format, each client keeps its own install records and enablement file — the "per-agent descriptor" problem does not go away.

---

## 4. Cursor, VS Code, Windsurf: editor extensions and Open VSX

### 4.1 VS Code extensions (the substrate)

- **Install state**: extensions unpack into `~/.vscode/extensions/<publisher>.<name>-<version>[-<platform>]/`, indexed by `~/.vscode/extensions/extensions.json` (array of `{identifier{id,uuid}, version, location, relativeLocation, metadata{publisherId, …}}`, observed) with pending removals listed in `.obsolete`. Relocatable via `--extensions-dir` / `VSCODE_EXTENSIONS` ([docs](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace)).
- **Enabled state**: not in any settings file. Global disables live in the SQLite `User/globalStorage/state.vscdb`, table `ItemTable`, key `extensionsIdentifiers/disabled` (value e.g. `[{"id":"github.copilot-chat"}]`, observed); workspace disables in the per-workspace `workspaceStorage/<hash>/state.vscdb`. Editing that DB while the editor runs does not take effect and is overwritten ([vscode#151985](https://github.com/microsoft/vscode/issues/151985), [code-server discussion](https://github.com/coder/code-server/discussions/7559)).
- **CLI**: `code --list-extensions --show-versions`, `--install-extension`, `--uninstall-extension`; `--disable-extension <id>` applies to that launch only — there is no persistent disable from the CLI.
- **Controls**: marketplace signature verification (`extensions.verifySignature`), a publisher-trust prompt since 1.97, the `extensions.allowed` allowlist policy, auto-update with `extensions.autoUpdateDelay`.

### 4.2 Cursor

Cursor now has *two* plugin systems:

- **Editor extensions** from **Open VSX**, served through Cursor's proxy `marketplace.cursorapi.com`, which runs "automated malware and supply-chain analysis … Extensions that fail review are blocked"; plus publisher verification via forum request, admin **install cooldown**, **Allowed extensions** lists and optional required Open VSX signatures ([Cursor extensions help](https://cursor.com/help/customization/extensions)). Extension files live in `~/.cursor/extensions/`; enabled state follows VS Code's `state.vscdb` model.
- **Cursor plugins** (Cursor 2.5, [announcement](https://cursor.com/blog/marketplace), [docs](https://cursor.com/docs/plugins)): `.cursor-plugin/plugin.json` bundling rules, skills, agents, commands, MCP servers and hooks; Agent Plugins 1.0 packages load natively (with `${CURSOR_PLUGIN_ROOT}` rather than the standard's `${PLUGIN_ROOT}` in `mcp.json`). Installed through **Customize** or `/add-plugin`, at user or workspace scope; local development plugins in `~/.cursor/plugins/local`. Admin distribution modes **Default Off / Default On / Required** (Required cannot be uninstalled); team marketplaces (1 on Teams, unlimited on Enterprise). Cursor states "every plugin is manually reviewed before it's listed" and all must be open source ([spec repo](https://github.com/cursor/plugins)).

### 4.3 Windsurf / Devin Desktop and other forks

Windsurf was renamed Devin Desktop on 2026-06-02 ([Cognition](https://devin.ai/blog/windsurf-is-now-devin-desktop/)); like VSCodium, Positron and Antigravity it uses Open VSX for editor extensions, with MCP wired separately into the agent. The shared weakness of the forks was shown in January 2026: they shipped VS Code's built-in *recommendations* for extension ids that did not exist on Open VSX, so anyone could register those names ([The Hacker News](https://thehackernews.com/2026/01/vs-code-forks-recommend-missing.html)); Cursor, Windsurf and Google patched, and the Eclipse Foundation removed the squatters.

---

## 5. OpenCode plugins (code modules)

OpenCode (~210k stars as of 2026-09, [anomalyco/opencode](https://github.com/anomalyco/opencode)) treats a plugin as a **JS/TS module exporting async functions** that receive `{project, client, $, directory, worktree}` and return a hooks object (`tool.execute.before`, event handlers, custom tools, compaction hooks) ([docs](https://opencode.ai/docs/plugins)).

- **Sources**: npm package names in the `plugin` array of `opencode.json` (global `~/.config/opencode/opencode.json` or project), and files auto-loaded from `~/.config/opencode/plugins/` and `.opencode/plugins/`.
- **Install state**: npm plugins are installed by Bun at startup into `~/.cache/opencode/node_modules/`; there are no install records beyond the config array. Load order: global config → project config → global dir → project dir; all hooks run in sequence.
- **Enable/disable**: none. A proposal for `disabled_plugins` plus `plugin list|enable|disable` ([#11743](https://github.com/anomalyco/opencode/issues/11743)) was closed as a duplicate; the implementing PR #12490 is unmerged, and a follow-up ([#44452](https://github.com/anomalyco/opencode/issues/44452), 2026-08-23) reports the feature still absent in 1.18.21. Disabling means deleting the array entry or moving the file.

The lesson: with code-module plugins there is nothing declarative to inspect — you cannot list a plugin's "components" without executing it, so an outside inventory can show only the package name and source.

---

## 6. Gemini CLI extensions

Gemini CLI (~107k stars) was deprecated for consumer accounts on 2026-06-18 in favour of the closed-source Antigravity CLI ([Google Developers Blog](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/)), but its extension model is the cleanest example of **path-scoped enablement** ([extension reference](https://github.com/google-gemini/gemini-cli/blob/main/docs/extensions/reference.md)):

- **Package**: `gemini-extension.json` (`name`, `version`, `mcpServers`, `contextFileName`, `excludeTools`, `settings[]` with `envVar` and `sensitive`), plus `commands/*.toml`, `hooks/hooks.json`, `skills/`, sub-agents, policies, themes. A `settings.json` MCP server of the same name overrides the extension's.
- **Install state**: `~/.gemini/extensions/<name>/`; `gemini extensions link <path>` symlinks a dev checkout.
- **Enabled state**: `~/.gemini/extensions/extension-enablement.json`, mapping each extension name to `{ "overrides": [ "/abs/path/*", "!/other/path/" ] }` — a list of path globs, `!` meaning disable, trailing `*` meaning include subdirectories, **last matching rule wins** ([extensionEnablement.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/cli/src/config/extensions/extensionEnablement.ts)). `--scope workspace` appends a rule for the current directory; `--scope user` a rule for `/`. `-e/--extensions` on the command line overrides everything for one run.
- **CLI**: `gemini extensions install|uninstall|update [--all]|enable|disable [--scope user|workspace]|config|new|link` — the full verb set, all persistent.
- Past bug: `gemini extensions disable` initially had no effect ([#9759](https://github.com/google-gemini/gemini-cli/issues/9759)).

---

## 7. Continue

Continue's "hub blocks" are fragments of `~/.continue/config.yaml` — `models`, `context`, `rules`, `prompts`, `docs`, `mcpServers`, `data` — referenced as `uses: owner/block` with `with:` (secrets) and `override:` ([reference](https://docs.continue.dev/reference)). There is no separate install or enabled state: adding or removing the YAML entry *is* install / uninstall, which makes it trivially manageable from outside but gives no bundle to inspect or toggle as a unit.

---

## 8. Third-party managers and browsers

| Tool | Stars (2026-09) | What it does with plugins |
| --- | --- | --- |
| [cc-switch](https://github.com/farion1231/cc-switch) | ~136k | Multi-agent provider switcher (Claude Code, Codex, Gemini CLI, OpenCode, …) with unified MCP and Skills panels backed by `~/.cc-switch/cc-switch.db`; **no plugin inventory**. Its FAQ "My plugin configuration disappeared after switching providers" is the instructive part: switching providers rewrote the agent's settings file wholesale and dropped `enabledPlugins`; the fix is a "Shared Config Snippet" carried across providers. |
| [claude-code-templates / aitmpl.com](https://github.com/davila7/claude-code-templates) | ~32k | Web catalog + CLI installer of agents, commands, MCP configs and plugins; install-oriented, not a state manager. |
| [claudemarketplaces.com](https://claudemarketplaces.com/) | n/a | Directory of plugins, skills and marketplaces ranked by installs and stars. |
| [ccpm](https://github.com/kaldown/ccpm) | ~50 | Rust TUI "lazygit for Claude Code plugins": reads `installed_plugins.json` (using `projectPath` for project/local installs) and `known_marketplaces.json`, toggles by editing `enabledPlugins` in the three scope files with **atomic writes and file locking**, encodes precedence Local > Project > User, and does **not** uninstall. |
| [SkillDock](https://github.com/wanghuan9/skilldock) | ~600 | Desktop skill manager across Claude Code, Cursor, Codex, Windsurf, Gemini; skills, not plugins. |

No widely adopted tool offers a *cross-agent* plugin inventory; the managers that exist either install (catalogs) or toggle one agent (ccpm).

---

## 9. Supply-chain incidents and what they teach

| When | Incident | Mechanism | Lesson for a plugin manager |
| --- | --- | --- | --- |
| May–Jun 2025 | Open VSX `publish-extensions` flaw ([Koi](https://blog.koi.security/marketplace-takeover-how-we-couldve-taken-over-every-developer-using-a-vscode-fork-f0f8cf104d44), [THN](https://thehackernews.com/2025/06/critical-open-vsx-registry-flaw-exposes.html)) | The nightly GitHub Actions job that republishes extensions exposed the `@open-vsx` service account's token, which could publish or overwrite any extension; disclosed 2025-05-04, patched 2025-06-25 | A registry is one credential away from pushing to every user; auto-update amplifies it. |
| Oct 2025 → 2026 | **GlassWorm** ([Koi](https://www.koi.ai/incident/live-updates-glassworm-first-self-propagating-worm-using-invisible-code-hits-openvsx-and-vscode-marketplaces), [THN](https://thehackernews.com/2025/10/self-spreading-glassworm-infects-vs.html)) | Invisible Unicode (PUA) payloads invisible in editors; Solana transaction memos as C2; steals npm/GitHub/Open VSX tokens and republishes with them (self-propagating); 7 extensions / ~35.8k downloads in the first wave | Code review of what is on disk can miss it; a manager showing "what is installed, from which publisher, at which version" is the first response tool. |
| Oct 2025 | Eclipse Foundation response ([heise](https://www.heise.de/en/news/Open-VSX-Eclipse-Foundation-Draws-Consequences-from-GlassWorm-Attack-10965519.html)) | Revoked tokens, shorter token lifetimes, scannable `ovsxat_` prefix, publish-time malware checks | Registry controls help but lag. |
| Jan–Mar 2026 | GlassWorm sleeper wave ([Socket](https://socket.dev/blog/glassworm-sleeper-extensions-activated-on-open-vsx), [THN: 72 extensions](https://thehackernews.com/2026/03/glassworm-supply-chain-attack-abuses-72.html)) | Benign extensions later updated to add `extensionPack` / `extensionDependencies` pointing at malicious ones — transitive install without user action; hit VS Code, VSCodium, Cursor, Windsurf, Positron | Dependencies are installs the user never chose; show them as such (Claude Code's `prune` and "auto-installed" labelling is the right idea). |
| Jan 2026 | Fork recommendation squatting ([THN](https://thehackernews.com/2026/01/vs-code-forks-recommend-missing.html)) | Forks recommended extension ids missing from Open VSX | Names are not identity; qualify ids by registry/marketplace. |
| Jan 2026 | Marketplace skill dependency hijack (PoC, [SentinelOne/Prompt Security](https://www.sentinelone.com/blog/marketplace-skills-and-dependency-hijack-in-claude-code/)) | A plugin skill quietly redirects `pip install` to an attacker index | Enabled plugins shape every future session; "enabled" is a standing grant, not a one-off. |
| Feb 2026 | **ClawHavoc** ([Koi](https://www.koi.ai/blog/clawhavoc-341-malicious-clawedbot-skills-found-by-the-bot-they-were-targeting), [THN](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html)) | 341 (later 824; 1,184 historically per Antiy) malicious OpenClaw skills whose "install prerequisites" steps fetched AMOS stealers | Instructions in a SKILL.md are an install vector even without code. |
| May 2026 | Malicious skills via dynamic context ([Datadog](https://securitylabs.datadoghq.com/articles/malicious-skills-supply-chain-risks-in-coding-agents-with-dynamic-context/)) | `!`command`` lines in a skill run before the model sees the skill (e.g. `gh auth token` exfiltration) | Model-level refusals do not protect; surfacing a plugin's skills and hooks for inspection has real value. Mitigation: `disableSkillShellExecution` in managed settings. |
| Disclosed Sep 2026 | **Plugin4Shell** ([Air Security](https://www.air.security/blog-posts/plugin4shell)) | SHA-pinned git plugin sources: attacker creates a *branch named like the pinned SHA* (or `FETCH_HEAD` for Gemini CLI), so checkout resolves to attacker code while the pin "looks honoured"; zero-click RCE. Fixed in Claude Code 2.1.179 and Codex 0.146.0; Copilot unpatched, Gemini CLI deprecated | A pin is only as good as the client that resolves it; a manager should show the *resolved* commit (`gitCommitSha`, `last_revision`) next to the declared one, and the agent version. |

---

## 10. Comparison

| | Claude Code | Codex | Cursor plugins | VS Code / forks | OpenCode | Gemini CLI |
| --- | --- | --- | --- | --- | --- | --- |
| Package manifest | `.claude-plugin/plugin.json` (optional) | root `plugin.json` (Agent Plugins) or `.codex-plugin/plugin.json` | `.cursor-plugin/plugin.json` or Agent Plugins | `package.json` in VSIX | none (JS module) | `gemini-extension.json` |
| Bundles | skills, commands, agents, hooks, MCP, LSP, styles, monitors, bin | skills, MCP, apps, hooks | rules, skills, agents, commands, MCP, hooks | arbitrary code | hooks + tools | MCP, commands, hooks, skills, context |
| Marketplace file | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` (+ Claude format) | `.cursor-plugin/marketplace.json` | registry (MS / Open VSX) | npm | git URL / gallery |
| Enabled state | `enabledPlugins` in 4 settings scopes | `[plugins."id"].enabled` in `config.toml` | app state (Customize UI) | SQLite `state.vscdb` | presence in config array | `extension-enablement.json` path rules |
| Install records | `installed_plugins.json`, `known_marketplaces.json` (internal) | `config.toml` + cache | app-managed | `extensions.json` + dir | Bun cache | extension dir |
| Code location | `~/.claude/plugins/cache/<mkt>/<p>/<ver>/` | `~/.codex/plugins/cache/<mkt>/<p>/<ver>/` | app-managed | `~/.vscode/extensions/` | `~/.cache/opencode/node_modules/` | `~/.gemini/extensions/` |
| Own enable/disable CLI | yes (`--scope`, `--json`) | no (TUI or config edit; app-server config write) | no | launch-only | no | yes (`--scope`) |
| Own uninstall CLI | yes (`--scope`, `--keep-data`, `--prune`) | yes (`codex plugin remove`) | no | yes | no | yes |
| Sub-plugin granularity | no | per bundled MCP server and tool | per MCP server / rule mode | no | no | `excludeTools` |
| Org control | managed `enabledPlugins`, `strictKnownMarketplaces`, `blockedMarketplaces` | admin policy Available/Installed/Not available | Default Off/On/Required, allowlists, cooldown | `extensions.allowed` | none | none |

---

## Patterns and trade-offs

- **Everyone converges on `name@marketplace` identity.** Claude Code, Codex and Cursor all qualify a plugin by its catalog; bare names collide (the fork-squatting incident is what happens without it).
- **Enablement is a sparse override map, not a list of installed things.** Claude Code and Codex store only explicit decisions (`true`/`false`), falling back to a default (`defaultEnabled`, marketplace policy). An absent key means "default", which is different from `false`; a writer that deletes keys to disable, or rewrites the whole file, changes meaning.
- **Split between editable config and internal bookkeeping.** Claude Code separates `enabledPlugins` (documented, user-editable) from install records and cache (undocumented, agent-owned). Codex puts both enablement and marketplace records into the user's `config.toml`, and writes its own bookkeeping keys (`last_revision`) there — so an outside writer of that file must preserve keys it does not understand. VS Code hides enablement in a SQLite DB that is only safely writable while the editor is closed.
- **Scope is where the field splits most.** Claude Code: four file scopes with project-over-user and managed-over-all precedence. Gemini CLI: path-glob rules, last match wins — any directory granularity. Codex: essentially one user file plus admin policy. Cursor/VS Code: global vs workspace in app state. A manager that shows a single "enabled" boolean hides *why* a plugin is on.
- **Uninstall is always the agent's job.** Every agent that supports uninstall does more than delete a config key — cache orphaning with a grace period, data-dir removal, dependency pruning, cross-scope prompts. The only agents where "uninstall" is a pure config edit are those with no install state at all (OpenCode, Continue).
- **The portable format stops at the package.** Agent Plugins 1.0 standardises the directory, not install state, enablement, marketplace or provenance; per-agent adapters remain necessary.
- **Activation is not immediate.** Claude Code defers plugin changes to `/reload-plugins` or the next session (prompt-cache cost); VS Code needs a reload; Codex's TUI refreshes on its own. An outside toggle is a request that takes effect later.

## Worth borrowing / worth avoiding

**Borrow**

- **Delegate state changes to the agent's own CLI when it has a machine-readable mode.** `claude plugin disable|uninstall --scope … --json` and `codex plugin remove` do the bookkeeping (orphaning, data dirs, dependency pruning) that a hand-written edit would miss.
- **Show scope provenance, not just a boolean.** "Enabled by project `.claude/settings.json`, overridden to off in `settings.local.json`" answers the question users actually have; ccpm and Claude Code's own scope-grouped Installed tab both do this.
- **Treat the enablement file as a merge target, not a document.** Edit one key, keep unknown keys and key order, write atomically with a lock (ccpm's approach); always leave an `enabledPlugins` object present in the base file, which also sidesteps the local-only silent drop.
- **Show what a plugin bundles.** Claude Code's `plugin details` (components + token cost) and "Not used recently" group, and Codex's per-bundled-MCP-server switches, turn an opaque bundle into something a user can judge.
- **Surface resolved provenance.** Marketplace source, resolved commit SHA vs declared version, whether it was auto-installed as a dependency, and whether it appears on the agent's own blocklist — the incidents above were all about installed code differing from what the user believed they had.
- **Honour the agent's own org policy.** A managed `true` cannot be turned off and a managed `false` cannot be turned on; a manager offering those toggles would produce writes the agent ignores.

**Avoid**

- **Rewriting a settings file wholesale** — cc-switch's provider switch dropping `enabledPlugins` is the canonical failure.
- **Writing internal records** (`installed_plugins.json`, `known_marketplaces.json`, VS Code's `state.vscdb`, caches). Their formats are undocumented and versioned (`"version": 2`), the agent rewrites them, and a running editor overwrites DB edits.
- **Writing the user-scope file to disable a project-enabled plugin.** Project beats user in Claude Code; the write succeeds and changes nothing.
- **Owning install or marketplace management.** Every incident in §9 enters through install, update or dependency resolution; that surface needs the agent's pinning, trust dialogs and org allowlists, which an outside tool would have to replicate exactly.
- **Assuming one plugin model.** Bundles, VSIX extensions, code modules and config blocks need different inventories; code-module plugins cannot be introspected without running them.

