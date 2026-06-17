# Competitive Research — AI Coding Agent Plugin / Extension Ecosystems

> English: this file · 中文版: [agent-plugins.zh.md](./agent-plugins.zh.md)
>
> Internal competitive-research report for Coffer's plugin facet (spec 004
> workspace amendment). **Date:** 2026-06-16. **Method:** deep-research harness.
> **Provenance caveat:** 3 claims 3-vote/partial confirmed; the rest are
> primary-sourced from official docs/issue trackers but rate-limiting cut
> re-verification short. Treat as primary-sourced, flag for a light fact-check.

## 1. Landscape at a glance

"Plugin/extension" means very different things per agent. Three models coexist:

| Model                         | Mechanism                                                                              | Agents                                 |
| ----------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------- |
| **Bundled-component plugins** | A directory bundling skills/subagents/hooks/MCP/commands, installed from a marketplace | Claude Code                            |
| **VS Code extension reuse**   | Open VSX (not MS Marketplace) VSIX extensions + a separate MCP layer                   | Cursor, Windsurf (now "Devin Desktop") |
| **Code-module plugins**       | JS/TS modules / config blocks loaded from npm or filesystem                            | OpenCode, Continue.dev                 |

### The players

- **Claude Code plugins** — a plugin is a self-contained directory whose
  components include **skills (slash commands), agents/subagents, hooks, MCP
  servers, LSP servers, and monitors**. [confirmed 3-0 —
  code.claude.com/docs/plugins-reference] Install is a **two-step marketplace
  flow** (add a marketplace catalog, then `/plugin install name@marketplace`),
  with `/plugin enable|disable|uninstall` verbs and a `--scope` flag.
  **State is split across two surfaces:** the _user-facing_ enable/disable lives
  in `settings.json`-family files under `enabledPlugins` (a `plugin@marketplace
→ bool` map, keyed by scope: user `~/.claude/settings.json`, project
  `.claude/settings.json`, local `.claude/settings.local.json`) [confirmed 3-0],
  while the _internal_ install state lives in `~/.claude/plugins/cache`
  (versioned copies, orphaned + auto-removed 7 days after uninstall) and
  `~/.claude/plugins/installed_plugins.json` (install records). **This is
  exactly the config-vs-internal-state boundary Coffer's design respects.** A
  documented gotcha: a local-scope `enabledPlugins` override is **silently
  dropped** if the key is absent from `settings.json`. [github.com/anthropics/
  claude-code issues #15524, #25086]
- **Cursor** — reuses the VS Code extension model but sources from the **Open
  VSX registry**, not Microsoft's Marketplace; enable/disable state lives in
  Cursor's internal SQLite (not a user-editable config file). [cursor.com/help]
- **Windsurf / Devin Desktop** — also sources editor extensions from **Open
  VSX**; MCP is a **separate integration layer** wired into the Cascade agent,
  not a marketplace extension. [docs.windsurf.com]
- **OpenCode** — plugins are an **array of npm package names** under the
  `plugin` key in `opencode.json`, plus local plugin files auto-loaded from
  `.opencode/plugins/` and `~/.config/opencode/plugins/`. A plugin is a JS/TS
  **module exporting functions** (receiving a context, returning hooks) — code,
  not a declarative bundle. MCP is separate (`mcp` key, per-server `enabled`
  bool). **As of early 2026 there is no built-in enable/disable command** — you
  edit the config or uninstall; a `disabled_plugins[]` array is only proposed.
  [opencode.ai/docs; issue #11743]
- **Continue.dev** — `config.yaml` blocks (models, context, rules, prompts/
  slash-commands, docs, mcpServers, data); references hub blocks via
  `uses: owner/blockname`. [docs.continue.dev]

### Security — the backdrop

The shared VS Code substrate is under active supply-chain attack: the **Wiz**
report on VS Code extension-marketplace supply-chain risk, the **GlassWorm**
worm abusing 70+ extensions, and **Open VSX** trust-gap research (ox.security's
"verified symbol" exploit) all landed in early 2026. Extension/plugin install is
a genuine attack surface — relevant to _why_ Coffer stays out of install.

## 2. Capability comparison

| Capability              | Claude Code                       | Cursor          | Windsurf    | OpenCode     | Continue.dev  | **Coffer plugin facet**                |
| ----------------------- | --------------------------------- | --------------- | ----------- | ------------ | ------------- | -------------------------------------- |
| Plugin can bundle       | skills/agents/hooks/MCP/LSP       | VSIX            | VSIX + MCP  | JS/TS module | config blocks | n/a (manages, doesn't author)          |
| Install / marketplace   | ✅ 2-step                         | ✅ Open VSX     | ✅ Open VSX | npm/fs       | hub `uses:`   | **❌ deliberately out of scope**       |
| Enable/disable surface  | `enabledPlugins` in settings.json | internal SQLite | —           | edit config  | config.yaml   | **✅ toggle (where documented)**       |
| Uninstall               | ✅                                | ✅              | ✅          | edit config  | edit config   | **✅ where config surface allows**     |
| Internal state writes   | cache + installed_plugins.json    | SQLite          | —           | —            | —             | **✅ never touches these**             |
| Read-time inventory     | —                                 | —               | —           | —            | —             | **✅ derived, grouped by marketplace** |
| Cross-agent plugin view | ❌                                | ❌              | ❌          | ❌           | ❌            | **possible (not yet built)**           |

## 3. How Coffer compares

Coffer's plugin facet does the **minimum on purpose**: list an agent's plugins
read-time (grouped by marketplace, never stored); toggle enable/disable and
uninstall **only where the agent's documented config surface supports it**
(dispatched by a per-agent capability descriptor: a plugin-model discriminator +
`can_toggle`/`can_uninstall` + which config file is the write surface); and
**never write the agents' internal state files.**

**The research validates this scoping.**

1. **The "never touch internal state" rule matches the documented boundary.**
   Claude Code itself separates user-facing `enabledPlugins` (in settings.json)
   from internal `~/.claude/plugins/cache` + `installed_plugins.json`. Writing
   the internal files would fight the agent's own bookkeeping; Coffer writing
   only `enabledPlugins` is exactly right.
2. **The per-agent descriptor maps to real heterogeneity.** The agents genuinely
   differ — Claude Code (toggle via `enabledPlugins`; no clean uninstall),
   Codex (toggle + uninstall), OpenCode (no built-in disable — must edit config),
   Cursor (Open VSX; state in SQLite → read-only is the correct call). A
   data-driven `can_toggle`/`can_uninstall` descriptor is the right abstraction
   for that spread.
3. **Staying out of install dodges the live attack surface.** Given GlassWorm /
   Open VSX / VS-Code-marketplace supply-chain attacks, _not_ owning install
   means Coffer doesn't inherit that risk. Visibility + safe toggle covers the
   recurring need.

**Where Coffer could extend (without breaking the scope).**

1. **Cross-agent plugin inventory.** One view of every plugin across every agent
   — none of the agents offer this, and it is a natural fit for Coffer's
   registry.
2. **Plugin → hub bridge (the novel move).** A Claude Code plugin _bundles_ MCP
   servers and skills. Coffer could ingest a plugin's shareable components (its
   MCP servers, its skills) INTO the hub and redistribute them to all agents —
   extending ingest→hub→deliver to the plugin layer. No competitor does this.
3. **Marketplace-trust signals.** Surface provenance ("this plugin came from an
   unverified Open VSX namespace") given the supply-chain climate.
4. **Handle the settings-merge gotcha** (local `enabledPlugins` silently dropped
   when absent from `settings.json`) in the safe-edit path.

## 4. Key takeaways for Coffer

1. **The "visibility + safe toggle/uninstall, no install" scope is the right
   call** — validated by both the config-vs-internal-state boundary and the live
   supply-chain threat to plugin install. Keep it.
2. **Your never-write-internal-state discipline is exactly correct** and matches
   Claude Code's own documented split. Don't drift from it.
3. **Biggest opportunity: the plugin → hub bridge.** Ingesting a plugin's bundled
   MCP/skills into Coffer's hub is unique to your hub-and-spoke model and turns
   a per-agent plugin into a shared asset.
4. **Cheap, high-value adds:** a cross-agent plugin inventory and
   marketplace-trust flags, both justified by the 2026 supply-chain attacks.

## 5. Sources

Primary:

- code.claude.com/docs/en/plugins-reference · code.claude.com/docs/en/discover-plugins
- github.com/anthropics/claude-code issues #15524, #25086
- cursor.com/help/customization/extensions
- docs.windsurf.com/windsurf/recommended-plugins · …/cascade/mcp
- opencode.ai/docs/plugins · opencode.ai/docs/config · github.com/anomalyco/opencode issue #11743
- docs.continue.dev/reference

Security:

- wiz.io/blog/supply-chain-risk-in-vscode-extension-marketplaces
- thehackernews.com/2026/03 — GlassWorm supply-chain attack (72 extensions)
- ox.security — "Can you trust that verified symbol" (IDE extension exploit)
- developer.microsoft.com/blog — security & trust in VS Marketplace
