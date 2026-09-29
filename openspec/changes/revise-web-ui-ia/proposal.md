## Why

The web UI is being rebuilt in place: a new shell, a new design system and new pages for each
domain. Before any of that lands, the information architecture it implements has to be the
contract, because the current specs pin the old one — eleven sidebar entries in three role
groups, an index that redirects to Agents, five Settings tabs, seven agent detail tabs, no page
for stored secrets, and a daemon the user is never shown.

Seven decisions change that architecture:

- **The sidebar grouped by what the user comes to do.** Three role groups put seven entries
  under Resources as soon as Secrets arrives, and nine once the planned Rules and Sources do.
  Five intent groups — Agents, Work, Capabilities, Context, System — hold the thirteen entries
  today and the roughly seventeen the roadmap names without any group passing five
  ([The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)).
- **A Secrets page.** A stored secret is cited by MCP servers, providers, channels and skills at
  once, and no page lists them or says what uses each. Secrets becomes its own System entry;
  Settings › Security keeps only what is about this machine.
- **Six agent detail tabs.** Skills, MCP servers and Plugins were three tabs answering one
  question — what is installed into this agent — and the model choice sat on Overview. They
  become Overview, Installed, Config files, Conversations, Memory and Model.

- **A landing page.** Opening the app should show the whole vault — what is healthy and what
  needs the user — before any one part of it. Landing on Agents shows one kind and hides the rest.
- **The daemon made visible.** Hiding the daemon left a user unable to tell "healthy" from "not
  yet known", or to see which build and port are answering and whether it starts at login, without
  a terminal. The daemon's state becomes visible at all times; starting it stays automatic.
- **Settings regrouped.** Experimental features get their own tab, the daemon gets one, and
  Coffer's own model moves beside the providers it is chosen from.
- **A command palette and attention dots.** With thirteen entries and many objects, the user needs
  one keystroke to reach any page or object, and one mark on the entry that needs them.

This change is the contract step. It ships together with the shell implementation, so it stays
unarchived until that implementation lands.

## What Changes

- The sidebar becomes an ungrouped **Overview** entry above five groups — **Agents** (Agents,
  Model providers), **Work** (Chat, Channels), **Capabilities** (MCP servers, Skills),
  **Context** (Knowledge, Memory), **System** (Secrets, Activity, Sync, Settings) — thirteen
  entries. Experimental switches hide entries exactly as before, and a group left with no entry
  hides its heading. Routes do not move.
- One name per surface in both languages, with the zh glossary fixed: 总览 · 智能体（智能体、模型提供商）
  · 工作（聊天、消息渠道）· 能力（MCP 服务器、技能）· 上下文（知识、记忆）· 系统（密钥、活动、同步、设置）;
  an agent is 智能体 everywhere in the zh UI.
- A **Secrets** page (`/secrets`) lists every stored secret with its presence and what uses it,
  and carries add, replace, reveal (audited), delete (refused while cited) and the entry to the
  migration assistant. Its behaviour beyond today's credential routes is specified by a separate
  secrets change.
- The agent detail page has six tabs: **Overview, Installed, Config files, Conversations, Memory,
  Model**. Installed groups the agent's skills, MCP servers, plugins and hooks in sections; Config
  files includes the instructions files (`CLAUDE.md`, `AGENTS.md`); Model holds the per-agent
  connection and model choice that sat on Overview.
- `/` renders the Overview page in place instead of redirecting to `/agents`. Overview's content
  is specified separately.
- Settings has six tabs: **General, Features, Security, Data, Daemon, About**. Experimental
  features move from General to Features; the Start at login card moves from General to Daemon;
  Security holds machine-level items only.
- **Coffer's model** leaves Settings and becomes a tab of the Model providers page
  (`/model-providers?tab=coffer-model`); `/settings/engine` redirects there.
- The sidebar footer shows the daemon's state (connecting, running with its port, stopping,
  offline) and opens **Settings → Daemon**, which shows status, the host's restart, the port (read
  only, with the command that changes it), Start at login and a Rotate token control. Stopping the
  daemon stays CLI-only.
- A **command palette** (⌘K / Ctrl+K) jumps to any page or object. It carries no action that
  changes state.
- A sidebar entry carries an **attention dot** while its kind's attention signal is raised; Sync's
  existing mark becomes the first user of one shared rule.
- The desktop shell's Restart control and version-skew warning are rendered on Settings → Daemon
  as well as in the offline banner, and a restart may be chosen from there.

## Capabilities

### New Capabilities

### Modified Capabilities
- `web-ui`: the sidebar entry set and its five intent groups (Overview and Secrets added), one
  name per surface with the zh glossary, the Secrets page, landing on Overview, six Settings
  tabs with Security machine-level only, Coffer's model beside Model providers, the daemon footer and Settings → Daemon, the command
  palette, sidebar attention dots; the daemon-invisibility requirement is removed and daemon
  shutdown alone stays CLI-only.
- `daemon`: the status probe is the one source of the state the shell shows; the port is shown on
  Settings → Daemon and still changed only from the CLI.
- `desktop-app`: the Restart control and version-skew warning are also rendered on Settings →
  Daemon, and a restart chosen there is the same restart.
- `experimental-features`: features are switched on Settings → Features, and a switched-off
  feature's notice links there and its pages and objects leave the command palette.
- `internal-engine`: the engine's settings are shown on the Coffer's model tab of Model providers
  instead of in Settings.
- `agent-registry`: the Agents entry heads the Agents group; the agent detail page's six tabs,
  with the Installed tab's sections and instructions files under Config files.
- `skill-manager`: unmanaged skills are reached from the Skills section of the agent's Installed
  tab.
- `provider-switching`: Model providers sits in the Agents group, and per-agent connection and
  model selection moves to the agent's Model tab.

## Impact

- Frontend: `components/Layout.tsx`, `components/SidebarNav.tsx` (replaced), a new Secrets page,
  the agent detail page's tab set (`pages/AgentDetailPage.tsx` and `components/agents/*`), a new sidebar footer
  and command palette, `router.tsx` (index route, `/settings/*` tabs, `/settings/engine` redirect,
  Model providers tabs), `pages/settings/*` (Features and Daemon tabs, residency card moved),
  `pages/ModelProvidersPage.tsx`, the attention-dot hook generalised from `useSyncAttention`, i18n
  strings in both locales.
- Desktop: no Rust change; the frontend's credential-supplier module exposes the restart and skew
  check to the Daemon tab and footer.
- Backend and contracts: none; every screen reads routes that already exist
  (`/daemon/status`, `/daemon/residency`, `/daemon/rotate-token`, `/daemon/features`,
  `/credentials`, the kind list routes). Listing uncited secrets, the migration assistant and an
  agent's hooks read arrive with their own changes.
- Tests: web-ui, experimental-features, internal-engine, desktop-app, agent-registry,
  skill-manager and provider-switching acceptance markers for the new and renamed scenarios; e2e shell specs (`shell_cold_start`, `shell_settings`) and new ones
  for the palette, footer and Daemon tab.
- Docs: the new ADR
  [The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)
  (Proposed; on acceptance it supersedes
  [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md)), docs-site guides
  (`web-ui`, `agents`, `credentials`, `desktop-app`, `daemon`, `experimental-features`,
  `providers`, and the pages naming Settings → General or Settings → Coffer's model), the ADR
  [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md)
  that cites a renamed requirement, the Proposed ADR
  [Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md)
  where it names the Security page as the place secrets are listed, and the Purpose sections of
  `web-ui`, `desktop-app`, `internal-engine` and `credentials`.
