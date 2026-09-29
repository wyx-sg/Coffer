## 1. Shell layout and sidebar

- [ ] 1.1 Replace `components/Layout.tsx` and `components/SidebarNav.tsx` with the new shell: Overview ungrouped at the top, then Agents (Agents, Model providers), Run (Chat, Channels), Capabilities (MCP servers, Custom tools, Skills, CLIs), Context (Knowledge, Memory), System (Secrets, Activity, Usage, Sync); no Settings entry; no flag, the old components are deleted
- [ ] 1.2 Keep the experimental gate on Knowledge, Memory and Sync entries and the experimental marker, unchanged in behaviour; a group whose every entry is switched off renders no heading
- [ ] 1.3 Keep the collapsible icon rail and its `localStorage` memory, and the language switcher
- [ ] 1.4 Add the sidebar footer: connecting / running (with port) / stopping / offline from the existing status poll, desktop version warning through the credential-supplier module, click opens the Settings modal at `/settings/daemon`, icon with tooltip on the collapsed rail; the Settings gear beside it
- [ ] 1.5 Generalise `useSyncAttention` into one attention-dot component and per-entry signal map; Sync keeps its seen-on-visit rule; an unreadable signal renders no dot

## 2. Routes

- [ ] 2.1 `router.tsx`: `/` renders the Overview page in place (no redirect to `/agents`); `/agents` unchanged
- [ ] 2.2 Settings routes `/settings/general`, `/settings/security`, `/settings/data`, `/settings/daemon`, `/settings/about`, rendered as a modal over a background location; `/settings` opens General; a fresh load renders it over Overview; close control, Escape, outside click and Back return to the page underneath
- [ ] 2.2a ⌘, / Ctrl+, opens the Settings modal on General from any page (not while typing in a text field)
- [ ] 2.3 Model providers is one table with no tabs (no Coffer's model tab, no "who runs on what" view); `/settings/engine` and the existing legacy redirect `/settings/embedding` (kept only for old bookmarks; there is no embedding configuration) redirect to `/settings/general`
- [ ] 2.4 `/secrets` route for the Secrets page
- [ ] 2.4a `/usage` route for the Usage page; its content lands with the change that meters use
- [ ] 2.5 Agent detail routes `/agents/<type>` (Overview) and `/agents/<type>/{model,skills,mcp-servers,plugins,hooks,config,memory,conversations}`; entry, plugin and unmanaged-skill detail pages nested under their tab; the old `/agents/:uid` and `?tab=` addresses redirect to the matching path

## 3. Settings tabs

- [ ] 3.1 General: default page size and preferred editor only
- [ ] 3.2 Delete the Experimental features card (`ExperimentalFeaturesSettings`) from General; the feature notice (`FeatureGate`) says the feature is off and links to no Settings tab
- [ ] 3.3 Daemon: status card, host-dependent restart (shell Restart control / `coffer daemon restart` to copy), read-only port with the CLI command, Start at login card moved from General, Rotate token with a confirmation that closes only on success and installs the returned token; loading skeleton and offline state
- [ ] 3.4 Rebuild the engine page (`InternalEngineSettings`) as the Coffer's model section of General: Engine model and Speech to text pickers (provider, then that provider's models), a Test action each through `POST /api/v1/models/test-connection`, inline not-set / failing states, the call bound beside the engine picker and the upkeep rows below
- [ ] 3.4a Provider detail Overview: read-only Used by (agents with their model → the agent's Model tab; Coffer's engine / Speech to text → `/settings/general`), no switch control; library badge hints name Settings › General
- [ ] 3.5 Data keeps its contents; About adds the update check (task 3.6); Security keeps only the master-key card (machine-level items); no stop or shutdown control anywhere
- [ ] 3.6 About: running version, last-checked time, Check for updates, update-available state with Download and restart and download progress, busy and error states, through the credential-supplier module; in a browser the version and a line that the desktop app installs updates

## 4. Secrets page

- [ ] 4.1 `pages/SecretsPage.tsx`: list from `GET /api/v1/credentials` with presence and used-by (kind and current name, each linking to the resource's page); shared table, loading, empty and error states
- [ ] 4.2 Add and replace through `POST /api/v1/credentials` (the value never shown back); Reveal behind an explicit action through the audited read; Delete behind a confirmation, refused while cited with the citers named (`409 CREDENTIAL_IN_USE`), the row kept
- [ ] 4.3 Leave a slot for the migration assistant entry and the unused marker; both arrive with the separate secrets change

## 5. Agent detail tabs

- [ ] 5.1 `pages/AgentDetailPage.tsx`: nine tabs Overview, Model, Skills, MCP servers, Plugins, Hooks, Config files, Memory, Conversations; Hooks reads `GET /api/v1/agents/{uid}/hooks`
- [ ] 5.2 Overview: details (type, config directory, Coffer connection) with no Title or Name field; summary rows for Skills, MCP servers, Plugins and Hooks with Coffer / own counts, each opening its tab
- [ ] 5.3 Skills, MCP servers, Plugins tabs from `AgentSkillsTab`, `AgentMcpServersTab`, `AgentPluginsTab`: Coffer's and the agent's own entries in one table, one owner filter kept in the URL; Adopt and Remove duplicate on Skills and MCP servers (a direct entry that `matches_resource`, an own skill folder named like a delivered skill), enable / disable / Uninstall on Plugins; Hooks rows open their file
- [ ] 5.4 Model tab: move the connection and model selection from `AgentOverviewTab`; Config files lists the instructions files beside the settings files
- [ ] 5.5 Back links of `AgentMcpEntryPage`, `AgentPluginPage` and `UnmanagedSkillDetailPage` return to their tab
- [ ] 5.6 Agents list: two fixed rows (Claude Code, Codex) from the candidates and registered agents on every load; states not installed (install command to copy), config left behind — program not found (reinstall command to copy), installed but never run (Add, creating the config directory), not added (Add), Connected / Not connected / Needs repair (Connect, Repair); Add / Connect / Repair open a change preview before writing; row menu "Use a different config directory…" with the folder picker; first run Add both; delete the Detect agents button, the Add agent dialog and the list's row selection and bulk actions
- [ ] 5.7 Backend: registration of an `installed_never_run` agent creates its standard config directory with only Coffer's entries; candidates in that state are addable and their scan row names `coffer agent add`

## 6. Command palette

- [ ] 6.1 Palette component opened by ⌘K / Ctrl+K and by a sidebar search control; Pages group from the sidebar entries and Settings tabs; Objects group from the agent list and each listed kind's list hook, matched by title and name
- [ ] 6.2 Navigation only — no entry that sends a mutating request; switched-off features' pages and objects left out
- [ ] 6.3 Per-group loading and error rows, Pages-only offline state, no-results message; arrow keys, Enter, Escape with focus return
- [ ] 6.4 en / zh strings for the palette, footer, Daemon tab, the Coffer's model section, the Secrets page and the agent detail tabs
- [ ] 6.5 i18n glossary: `nav.*` keys for the five group headings, fifteen entries and the Settings gear, zh labels 总览 · 智能体（智能体、模型提供商）· 运行（聊天、消息渠道）· 能力（MCP 服务器、自定义工具、技能、命令行工具）· 上下文（知识、记忆）· 系统（密钥、活动、用量、同步）, Settings 设置; replace every zh "Agent" naming an agent with 智能体 across `zh.json`; record the en/zh glossary in `.agents/frontend.md`; extend `i18n/surfaceNames.test.ts` to the new entries

## 6b. Add server

- [ ] 6b.1 MCP servers page: one Add server action (drop the separate paste-JSON button); welcome card's primary action reads Add server
- [ ] 6b.2 Paste box recognising `mcpServers` JSON or a server object, Codex TOML `[mcp_servers.<name>]` tables, `claude mcp add` / `codex mcp add` / plain command lines (stdio) and URLs (Streamable HTTP); one server → prefilled form, several → review step; unreadable input → message and stdio / Streamable HTTP choice
- [ ] 6b.3 Review step: secret detection over env and headers, register-first then credentials, names normalised and editable with the 24-character flag, reach choice; Import from agents link in the dialog

## 6c. Custom tools and CLIs pages

- [ ] 6c.1 `/custom-tools`: list of `mcp_server` resources with a script, HTTP or OpenAPI transport, grouped by health; Add custom tool (Script / HTTP endpoint / OpenAPI → type form); detail with definition, Test, reach control, per-tool switch and the scoped calls table; the MCP servers list and Add dialog leave these out
- [ ] 6c.2 `/clis` and `/clis/<command>`: one row per required command with version vs minimum, login state, skills that need it, problems first; detail with Homebrew Install behind a confirmation naming the command, login command to copy, Check again
- [ ] 6c.3 Skill detail links each requirement to `/clis/<command>`; Overview attention item for a missing, outdated or logged-out required CLI; palette Objects include custom tools and CLIs
- [ ] 6c.4 Backend reads these pages need (custom-tool transports, skill `requires`, command probing) land with their own changes; until then the pages render from what those changes provide

## 6a. Auto-update (after the release is Apple Developer ID signed)

- [ ] 6a.1 Tauri updater plugin in the shell with the updater public key in the bundle configuration; check at launch and every six hours; IPC commands for check (version, last check, result) and install (download with progress, verify, replace, relaunch); failures recorded under `coffer.desktop` in the daemon log
- [ ] 6a.2 After the relaunch, a previous-version daemon found by the skew check is replaced through the one restart
- [ ] 6a.3 Release workflow: sign the updater archive with the updater key from repository secrets and publish the archive, its signature and the manifest beside the `.dmg`

## 7. Tests

- [ ] 7.1 `acceptance(web-ui, "the sidebar groups entries by what the user comes to do")` replaces "the sidebar groups agents, resources and system by role"; `acceptance(web-ui, "each listed resource kind has one sidebar entry")` replaces "resources holds one entry per kind with a list"; new `acceptance(web-ui, "a group with every entry switched off leaves the sidebar")`; `acceptance(web-ui, "a switched-off feature leaves the sidebar")` and "every resource entry opens a list page of its own" updated (`SidebarNav` tests); `acceptance(web-ui, "a surface carries one name in the sidebar and on its page")` updated for the glossary (`surfaceNames.test.ts`)
- [ ] 7.2 `acceptance(web-ui, "the index opens Overview")` replaces "the index opens the Agents page" (`router.test.tsx`)
- [ ] 7.3 `acceptance(web-ui, "cold-start renders authenticated content")` and `acceptance(web-ui, "daemon-offline banner appears when daemon is unreachable")` updated (`e2e/web/specs/shell_cold_start.spec.ts`)
- [ ] 7.4 `acceptance(web-ui, "settings layout uses the redesigned tabbed sidebar")` updated and `acceptance(web-ui, "settings offers no shutdown control")` replaces "settings drops the confusing controls" (`e2e/web/specs/shell_settings.spec.ts`); delete the marker for "settings shows no daemon tab and no daemon status" (`AboutPage.test.tsx`)
- [ ] 7.5 `acceptance(web-ui, "the settings daemon tab sets when the daemon runs")` replaces "the general tab sets when the daemon runs" (`DaemonResidencySettings.test.tsx`)
- [ ] 7.6 `acceptance(web-ui, …)` for "coffer's model is chosen in settings general", "an unset picker says what coffer does without it", "testing a picker shows a failing pair inline" and "the old coffer's model address opens settings general"; `acceptance(provider-switching, …)` for "the provider library has no tabs" and "a provider's used-by list is read-only"
- [ ] 7.7 `acceptance(web-ui, …)` for the footer: "the footer shows a running daemon", "the footer says connecting before the first answer", "the footer shows an offline daemon", "the footer shows a stopping daemon", "the collapsed rail keeps the daemon state"
- [ ] 7.8 `acceptance(web-ui, …)` for the Daemon tab: "the settings daemon tab shows the running daemon", "the settings daemon tab offers the host's restart", "the settings daemon tab shows the port without editing it", "rotating the token from the settings daemon tab keeps the page working", "a failed rotation from the settings daemon tab keeps the old token", "the settings daemon tab keeps its layout while status loads", "the settings daemon tab with the daemon offline"
- [ ] 7.9 `acceptance(web-ui, …)` for the palette: "the palette jumps to a page", "the palette jumps to an object", "the palette offers no actions", "the palette leaves out switched-off features", "the palette lists pages while objects load", "a failing kind leaves the rest of the palette working", "the palette with the daemon offline", "the palette says when nothing matches"; one e2e spec for page and object jumps
- [ ] 7.10 `acceptance(web-ui, …)` for the dots: "an entry whose kind needs attention carries a dot", "the attention dot stays on the collapsed rail", "an entry without a signal never carries a dot", "an unreadable signal leaves no dot"
- [ ] 7.11 `acceptance(daemon, "the status probe carries what the shell shows")` on a daemon-route integration test beside the status tests
- [ ] 7.12 Delete the marker for experimental-features "the general tab switches a feature" with `ExperimentalFeaturesSettings.test.tsx`; `acceptance(experimental-features, "a switched-off feature's page says it is switched off")` on `FeatureGate.test.tsx`
- [ ] 7.13 `acceptance(internal-engine, "the general tab's coffer's model section shows and changes both halves")` and `acceptance(internal-engine, "a failed test leaves coffer's model as it was")`; the first replaces "Settings → Coffer's model shows and changes both halves" (`EngineSettings.test.tsx`)
- [ ] 7.14 `acceptance(desktop-app, "the shell hosts the one build the daemon serves")` updated for the Daemon tab, About tab and footer as sanctioned host-conditional places (`test_desktop_shell_surface.py`); the restart scenarios keep their names and markers
- [ ] 7.14a `acceptance(desktop-app, …)` for "the shell checks at launch and every six hours", "an update is installed only with a valid signature" (`cargo test`), "installing an update relaunches onto the new version" (launching the app) and "a release publishes the update manifest" (release-workflow check)
- [ ] 7.14b `acceptance(web-ui, …)` for the Settings modal: "the gear opens Settings over the current page", "the keyboard shortcut opens Settings", "closing Settings returns to the page underneath", "a deep link opens a Settings tab", "the palette opens a Settings tab over the current page"; and for About: "about shows the version and when updates were last checked", "checking by hand finds a newer version", "download and restart installs the newer version", "a failed check keeps the last good result", "about in a browser offers no update control"
- [ ] 7.14c `acceptance(web-ui, …)` for "pasting JSON with three servers opens the review", "pasting a command line prefills a stdio server", "pasting a URL prefills a Streamable HTTP server", "pasting Codex TOML reads its server tables", "unreadable input offers a manual type choice" and "the add dialog links to importing from agents"; the existing markers under "Add MCP servers from one paste box", "Explain unreadable pasted input in the dialog" and "Welcome an empty list with one next action" follow the new label and flow
- [ ] 7.14d `acceptance(web-ui, …)` for "the custom tools page groups tools by health", "adding a custom tool starts by choosing its type", "a custom tool's detail page tests and switches its tools", "the CLIs page lists problems first", "installing a CLI asks first and uses Homebrew only", "check again after logging in", "a skill's requirement links to its CLI" and "overview flags a required CLI that needs attention"; the sidebar and palette markers follow the fifteen entries
- [ ] 7.15 Migrate the e2e shell specs to role and label locators for the new sidebar
- [ ] 7.16 `acceptance(web-ui, …)` for "the security tab keeps only machine-level settings", "the secrets page lists each secret with what uses it", "a secret in use cannot be deleted from the secrets page" and "revealing a secret is an explicit, audited read"
- [ ] 7.17 `acceptance(agent-registry, "the agent detail page carries nine tabs")` (`AgentDetailPage.test.tsx`); "open a plugin's detail page from the Plugins tab" and "open a direct MCP server's detail page from the agent" follow the tabs (`AgentPluginsTab`, `AgentPluginPage`, `AgentMcpEntryPage` tests); `acceptance(agent-registry, …)` for "the owner filter narrows an installed-kind tab", "a duplicate direct MCP entry can be removed", "the agents page shows both supported agents on first run", "an agent that is not installed shows how to install it", "a row's menu offers a different config directory", "the agents page detects candidates without a detect action", "adding an agent previews the change first", "repairing a partial connection previews the missing parts", "desktop app agents page", "pick a custom config directory with the native dialog", "an installed agent that has never run can be added", "a leftover config directory reads as config left behind", "add an agent that has never run" and "register an installed agent whose config directory is not created yet"; the tests behind "offer an installed agent that has never run" and "show a leftover config directory as not installed" follow their new bodies (the second keeps its name, since a MODIFIED requirement cannot rename a scenario, and its body now says config left behind); skill-manager "open an unmanaged skill's detail page from the agent's Skills tab" and "adopt or delete an unmanaged skill from its detail page" likewise (`AgentSkillsTab`, `UnmanagedSkillDetailPage` tests); provider-switching "the connections page lists profiles and their compatible agents" names the Model tab (`ModelProvidersPage.test.tsx`)

## 8. Docs

- [ ] 8.1 `docs-site/guides/web-ui.md`: the sidebar table with its five groups, Overview, Secrets and Usage, Settings as a gear and ⌘, modal with its five tabs, the footer, Settings → Daemon, the command palette and attention dots; rotating the token is now in the UI, stopping stays CLI-only
- [ ] 8.2 `docs-site/guides/desktop-app.md`: Restart from Settings → Daemon, the footer's version warning, Start at login under Settings → Daemon, updates checked at launch and every six hours and installed from Settings › About
- [ ] 8.3 `docs-site/guides/daemon.md`, `experimental-features.md`, `providers.md`, `channels.md`, `knowledge.md`, `memory.md`, `vault-sync.md`, `troubleshooting.md`, `faq.md`, `start/*`, `reference/configuration.md`, `architecture/distribution.md`: Settings → General → Experimental features is removed (switching stays on the CLI); Settings → General → Coffer's daemon becomes Settings → Daemon; Settings → Coffer's model becomes Settings › General → Coffer's model
- [ ] 8.4 `docs-site/guides/agents.md` (the two-row Agents list, Add with preview, nine detail tabs, owner filter, Model tab), `credentials.md` (the Secrets page; Settings › Security machine-level), `providers.md` (Model providers under Agents; per-agent selection on the Model tab), `channels.md` (Channels under Run)
- [ ] 8.5 ADR [The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md): on acceptance set it Accepted, mark [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md) `Superseded by` it (or delete it if nothing it explains is inherited) and move both rows in the README index; ADR [Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md): "the Security page" lists stored secrets becomes the Secrets page; ADR [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md): follow the rename of "Leave daemon controls to the CLI"
- [ ] 8.6 Purpose sections: `web-ui` (grouped by what the user comes to do, Overview above the five groups; drop "grouped by role"), `credentials` (its visual surfaces are the Secrets page and Settings › Security, not Security alone), `desktop-app` (Restart control and skew warning rendered in the banner and on Settings → Daemon; drop auto-update from Out of scope; the IPC command list gains the update check and install; the release publishes the updater archive and manifest), `internal-engine` (Settings › General → Coffer's model)
- [ ] 8.7 Code comments citing removed or renamed titles follow them (the list `scripts/check_spec_citations.py` prints): `useFeatures.ts`, `DaemonResidencySettings.tsx`, `InternalEngineSettings.tsx`, `backend/coffer/application/features.py` and the daemon contract `openspec/specs/daemon/contracts/api.openapi.yaml` ("Switch a feature from the command line")
- [ ] 8.8 `.agents/frontend.md`: the palette, footer and attention-dot components as shell conventions, and the en/zh glossary (task 6.5)

## 9. Verify and archive

- [ ] 9.1 `make verify` (including spec citations, acceptance audit, OpenSpec strict validation, doc numbering, file sizes and codegen check)
- [ ] 9.2 Archive the change in the same PR as the shell implementation (`npx openspec archive revise-web-ui-ia --yes`)
