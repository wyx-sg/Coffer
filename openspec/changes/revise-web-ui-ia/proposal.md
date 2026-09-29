## Why

The web UI is being rebuilt in place: a new shell, a new design system and new pages for each
domain. Before any of that lands, the information architecture it implements has to be the
contract, because the current specs pin the old one — eleven sidebar entries in three role
groups, an index that redirects to Agents, five Settings tabs, seven agent detail tabs, an Agents
list built around a Detect button and an Add agent dialog, no page
for stored secrets, and a daemon the user is never shown.

Eight decisions change that architecture:

- **The sidebar grouped by what the user comes to do.** Three role groups put seven entries
  under Resources as soon as Secrets arrives, and nine once the planned Rules and Sources do.
  Five intent groups — Agents, Run, Capabilities, Context, System — hold the fifteen entries
  of 1.0 (Usage, Custom tools and CLIs among them) with no group past four; at the roughly
  eighteen the roadmap names, Capabilities is the one group that would need revisiting
  ([The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)).
- **A Secrets page.** A stored secret is cited by MCP servers, providers, channels and skills at
  once, and no page lists them or says what uses each. Secrets becomes its own System entry;
  Settings › Security keeps only what is about this machine.
- **Nine agent detail tabs and a fixed Agents list.** The model choice sat on Overview and hooks
  had no tab. The page becomes Overview, Model, Skills, MCP servers, Plugins, Hooks, Config
  files, Memory and Conversations, each installed-kind tab listing Coffer's entries and the
  agent's own under one owner filter. The Agents list becomes the two supported agents, found
  automatically, each added with a previewed Add.

- **A landing page.** Opening the app should show the whole vault — what is healthy and what
  needs the user — before any one part of it. Landing on Agents shows one kind and hides the rest.
- **The daemon made visible.** Hiding the daemon left a user unable to tell "healthy" from "not
  yet known", or to see which build and port are answering and whether it starts at login, without
  a terminal. The daemon's state becomes visible at all times; starting it stays automatic.
- **Settings regrouped, and out of the sidebar.** The daemon gets its own tab, the Experimental
  features card leaves with the switches it held (every flag graduates at 1.0), and Coffer's own
  model becomes a section of General: machine-level configuration of Coffer itself. Settings
  is machine-level and visited rarely, so it leaves the sidebar for a modal opened from a gear in
  the sidebar footer or with ⌘,, still addressable at `/settings/<tab>`.
- **Updates found by the app.** A desktop user learns of a new version only by downloading a new
  `.dmg`. The shell checks a signed manifest on GitHub Releases at launch and every six hours,
  and Settings › About shows the result and installs it on request.
- **A command palette and attention dots.** With fifteen entries and many objects, the user needs
  one keystroke to reach any page or object, and one mark on the entry that needs them.

This change is the contract step. It ships together with the shell implementation, so it stays
unarchived until that implementation lands.

## What Changes

- The sidebar becomes an ungrouped **Overview** entry above five groups — **Agents** (Agents,
  Model providers), **Run** (Chat, Channels), **Capabilities** (MCP servers, Custom tools,
  Skills, CLIs), **Context** (Knowledge, Memory), **System** (Secrets, Activity, Usage, Sync) —
  fifteen entries. Usage's page is specified with the change that meters use.
- A **Custom tools** page (`/custom-tools`) manages HTTP API tools in groups: a group has a fixed
  name agents see as the prefix (`<group>__<tool>`), a shared base URL, an auth header bound to a
  secret that never reaches the agent, and a default reach; each tool has its own switch and an
  optional reach override. Add custom tool imports an OpenAPI spec (picking operations, creating a
  group that can be re-imported with a preview) or defines one request by hand in an existing or
  new group. Script tools are deferred past 1.0. The MCP servers Add dialog offers no custom
  tools.
- A **CLIs** page (`/clis`) lists every command a skill requires with its version against the
  minimum, login state and the skills that need it, problems first; its detail page installs
  through Homebrew after a confirmation, shows the login command and checks again. A skill's
  requirements link there, and Overview flags a required CLI that is missing, outdated or not
  logged in. Experimental switches hide entries exactly as before, and a group left with no entry
  hides its heading. Routes do not move.
- One name per surface in both languages, with the zh glossary fixed: 总览 · 智能体（智能体、模型提供商）
  · 运行（聊天、消息渠道）· 能力（MCP 服务器、自定义工具、技能、命令行工具）· 上下文（知识、记忆）· 系统（密钥、活动、用量、同步）,
  and Settings is 设置;
  an agent is 智能体 everywhere in the zh UI.
- A **Secrets** page (`/secrets`) lists every stored secret with its presence and what uses it,
  and carries add, replace, reveal (audited), delete (refused while cited) and the entry to the
  migration assistant. Its behaviour beyond today's credential routes is specified by a separate
  secrets change.
- The agent detail page has nine tabs, each at its own path (`/agents/<type>/<tab>`):
  **Overview, Model, Skills, MCP servers, Plugins, Hooks, Config files, Memory, Conversations**.
  Skills, MCP servers, Plugins and Hooks each list Coffer-managed and the agent's own entries with
  one owner filter and the kind's own actions (adopt, remove duplicate, uninstall plugin, open
  file); Overview's summary rows open those tabs and its details carry no Title or Name; Config
  files includes the instructions files (`CLAUDE.md`, `AGENTS.md`); Model holds the per-agent
  connection and model choice that sat on Overview. Hooks reads the hooks listing that already
  ships (`GET /api/v1/agents/{uid}/hooks`).
- The **Agents list** shows exactly two rows, Claude Code and Codex, detected automatically: no
  Detect agents button and no Add agent dialog. A row offers Add (with a change preview), Connect
  or Repair as its state calls for (Add also for an agent installed but never run, creating its config directory with only Coffer's entries), the install command when the agent is not installed, the reinstall command when only its config is left behind, and
  "Use a different config directory…" in its menu; first run offers Add both.
- `/` renders the Overview page in place instead of redirecting to `/agents`. Overview's content
  is specified separately.
- **Settings** is not a sidebar entry: a gear in the sidebar footer, beside the daemon status,
  and ⌘, / Ctrl+, open it as a large modal over the current page. Each tab keeps its route
  (`/settings/<tab>`), so deep links, the palette and other pages' links open the modal over the
  page underneath, and closing it returns there.
- Settings has five tabs: **General, Security, Data, Daemon, About**. The Experimental features
  card leaves General and no tab replaces it; the Start at login card moves from General to
  Daemon; Security holds machine-level items only.
- **Coffer's model** becomes a section of Settings › General: two pickers (Engine model, Speech
  to text), each choosing a provider and then one of its models, a Test action each, and inline
  not-set / failing states. `/settings/engine` opens Settings › General.
- **Model providers** is one connection table with no tabs: no Coffer's model tab and no view of
  which agent runs on what. A provider's detail page lists **Used by** read-only (agents with
  their model, linking to each agent's Model tab; Coffer's engine and Speech to text, linking to
  Settings › General); switching an agent's provider happens only on its Model tab.
- The sidebar footer shows the daemon's state (connecting, running with its port, stopping,
  offline) and opens **Settings → Daemon**, which shows status, the host's restart, the port (read
  only, with the command that changes it), Start at login and a Rotate token control. Stopping the
  daemon stays CLI-only.
- The MCP servers page has one **Add server** action. Its dialog opens on a paste box that
  recognises an `mcpServers` JSON block or server object, Codex TOML `[mcp_servers.<name>]`
  tables, a command line (`claude mcp add …`, `codex mcp add …` included) as stdio, or a URL as
  Streamable HTTP; one server opens the prefilled form, several open the review step (secrets to
  the credential store, names normalised and correctable, reach), and unreadable input says so
  and offers a manual type choice. Import from agents is a link in the same dialog.
- The **Skills page** lists only the skills Coffer manages; an agent's own skills and adopting
  them live on that agent's Skills tab, and the empty state only links there. A skill's detail
  page has four tabs — **Files · Delivery · Requires · History** — with no separate SKILL.md tab:
  Files opens with `SKILL.md` selected and rendered, a Preview / Source toggle and Edit.
- **Tab addresses** follow one rule on every detail page: `/<kind>/<id>/<tab>`, the default tab
  at the bare path, named by the resource's fixed name for skills, MCP servers and custom tool
  groups, by type for agents, by command for CLIs, and by `uid` for kinds that can be renamed; old
  `?tab=` and uid addresses redirect.
- Every **split view** (list/detail, file tree/file, conversation list/thread, the sidebar) resizes
  by dragging its divider, within minimum widths, with double-click to reset and ←/→ from the
  keyboard; the width is remembered per page in the browser, safe to lose.
- The agent **Model tab** carries Provider · Model · Effort, and for Claude Code off its built-in
  login a **Model per tier** section (Opus / Sonnet / Haiku, Fable when listed) that Coffer prefills
  and the user can edit or reset; no other model setting is shown. Claude Code gets the top-level
  `model` and `effortLevel`, the `ANTHROPIC_DEFAULT_<TIER>_MODEL` pins and a `modelPicker`; the
  deprecated `ANTHROPIC_SMALL_FAST_MODEL` and `env.ANTHROPIC_MODEL` are deleted on every write.
  Codex's catalogue carries each model's context window, a 90% auto-compact limit and its effort
  levels. A local model connection reads its window from the runtime (a required field when it
  cannot, a warning below 64k) and sets Claude Code's compatibility key. Switching back to the
  built-in login removes every key Coffer wrote.
- **Adding a skill** offers three sources — a folder, an archive (`.zip` / `.skill`, uploaded or
  `coffer skill add <file.zip>`) and a Git repository (URL, optional ref and subpath, pinned to a
  commit, with Update available, a previewed diff and a conflict view when the skill was edited
  locally) — each showing what it found before anything is written. Archives are checked for
  zip-slip, symlinks and size before they are read into the store. There is no create-from-scratch.
- **Knowledge:** Curate now drains a collection pass by pass with progress, stopping at the first
  failure; one term, Curate / Curation (整理), everywhere; an Inbox node with a count, a header
  status line, Add a document (submitted as an item, not written as a document), a body-only editor with Reload / Compare on a
  stale save, and no curation controls without Coffer's model. Every document has a History tab
  and every pass can be undone as a whole from a cross-collection Recent changes view, on the
  vault's git history. Leftover "disabled collection" wording is removed.
- A **memory partition** has two tabs: Memories (the UI's word for notes, 记忆条目), with a
  collapsed Retired group and a meta line naming the agents each was learned from and no native
  paths, agent text, `.raw/`, index or retired files or file tree; and Delivered, the exact
  session-start text each agent receives there.
- The **Memory overview** lists each agent's deliveries, memories read and last delivery over seven
  days. The delivery hook's state is shown only on the agent detail page (Hooks tab and Overview
  connection block); the agent's Memory tab shows only its native memory stores.
- A **command palette** (⌘K / Ctrl+K) jumps to any page or object. It carries no action that
  changes state.
- A sidebar entry carries an **attention dot** while its kind's attention signal is raised; Sync's
  existing mark becomes the first user of one shared rule.
- The desktop shell's Restart control and version-skew warning are rendered on Settings → Daemon
  as well as in the offline banner, and a restart may be chosen from there.
- **Auto-update.** The desktop shell checks for a newer version at launch and every six hours
  through the Tauri updater, against a signed manifest the release workflow publishes on GitHub
  Releases. Settings › About shows the running version, the last check, a Check for updates
  control and, when a newer version exists, Download and restart; an update whose signature does
  not verify is refused. In a browser About shows the version only.

## Capabilities

### New Capabilities

### Modified Capabilities
- `web-ui`: the sidebar entry set and its five intent groups (Overview, Secrets and Usage added,
  Settings moved to a footer gear and a route-addressable modal), the update check on Settings ›
  About, one
  name per surface with the zh glossary, the Secrets page, landing on Overview, five Settings
  tabs with Security machine-level only, Coffer's model in Settings › General, the daemon footer and Settings → Daemon, the command
  palette, sidebar attention dots, one Add server action whose paste box recognises JSON, Codex
  TOML, a command line or a URL; the daemon-invisibility requirement is removed and daemon
  shutdown alone stays CLI-only.
- `daemon`: the status probe is the one source of the state the shell shows; the port is shown on
  Settings → Daemon and still changed only from the CLI.
- `desktop-app`: the Restart control and version-skew warning are also rendered on Settings →
  Daemon, and a restart chosen there is the same restart; the shell checks for and installs
  signed updates, a third sanctioned host affordance rendered on Settings › About. The Purpose
  section's "auto-update is out of scope" is reversed with it.
- `experimental-features`: the web UI's Experimental features card is removed and the switch
  requirement no longer names a Settings page; a switched-off feature's notice says it is off, and
  its pages and objects leave the command palette.
- `knowledge`: the manual trigger drains until nothing is pending; the web UI terms, Inbox,
  status line, Add a document and editor; document history and whole-pass undo; no disabled
  collection anywhere.
- `memory`: a partition's page has Memories (with a Retired group and learned-from agents, none of
  the agents' own sources) and Delivered tabs; provenance stays in the data and CLI.
- `internal-engine`: the engine's settings are shown in the Coffer's model section of Settings ›
  General, with a provider-then-model picker and a Test action for the engine and for speech to
  text.
- `agent-registry`: the model binding carries `effort` and `tier_models` in place of `fast_model`;
  the Agents entry heads the Agents group; the agent detail page's nine tabs,
  the owner filter and per-kind actions, instructions files under Config files; the Agents list's
  two fixed rows with automatic detection, previewed Add / Connect / Repair, Add both and the
  row menu's config directory.
- `skill-manager`: skills are added from a folder, an archive or a Git repository, with
  `archive_import` and `git_import` sources; unmanaged skills are reached and adopted only from the agent's Skills tab, and
  the Skills page lists managed skills only; a skill's detail page has Files (opening on a
  rendered `SKILL.md` with Preview / Source and Edit), Delivery, Requires and History tabs.
- `provider-switching`: the Claude Code and Codex projections write the model keys above and
  revert every key Coffer wrote; the Model tab's fields, tier suggestions, per-model context window
  and effort levels, and local model connections; Model providers sits in the Agents group as one table with no tabs,
  per-agent connection and model selection moves to the agent's Model tab, and a provider's
  detail page lists what uses it read-only.

## Impact

- Frontend: `components/Layout.tsx`, `components/SidebarNav.tsx` (replaced), a new Secrets page,
  the agent detail page's tab set (`pages/AgentDetailPage.tsx` and `components/agents/*`), a new sidebar footer
  and command palette, `router.tsx` (index route, `/settings/*` tabs, `/settings/engine` redirect,
  Model providers tabs), `pages/settings/*` (Daemon tab, residency card moved, Experimental
  features card deleted),
  `pages/ModelProvidersPage.tsx`, the attention-dot hook generalised from `useSyncAttention`, i18n
  strings in both locales.
- Desktop: the Tauri updater plugin with its public key in the bundle configuration, a
  six-hour timer, and IPC commands for check and install; the frontend's credential-supplier
  module exposes the restart and skew check to the Daemon tab and footer, and the update check to
  the About tab. Release: the workflow signs the updater archive with the updater key held as a
  repository secret and publishes it with its manifest beside the `.dmg`.
- Backend and contracts: none; every screen reads routes that already exist
  (`/daemon/status`, `/daemon/residency`, `/daemon/rotate-token`, `/daemon/features`,
  `/credentials`, the kind list routes, `/agents/{uid}/hooks`). Listing uncited secrets and the
  migration assistant arrive with their own changes.
- Tests: web-ui, experimental-features, internal-engine, desktop-app, agent-registry,
  skill-manager and provider-switching acceptance markers for the new and renamed scenarios; e2e shell specs (`shell_cold_start`, `shell_settings`) and new ones
  for the palette, footer, Settings modal, Daemon tab and About tab's update states; the shell's
  `cargo test` for the update check's schedule and signature refusal.
- Docs: the new ADR
  [The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)
  (Proposed; on acceptance it supersedes
  [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md)), docs-site guides
  (`web-ui`, `agents`, `credentials`, `desktop-app`, `daemon`, `experimental-features`,
  `providers`, and the pages naming Settings → General or Settings → Coffer's model, which now name Settings › General), the ADR
  [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md)
  that cites a renamed requirement, the Proposed ADR
  [Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)
  where it names the Security page as the place secrets are listed, and the Purpose sections of
  `web-ui`, `desktop-app`, `internal-engine` and `credentials`.
