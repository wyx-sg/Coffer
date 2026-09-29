## 1. Shell layout and sidebar

- [ ] 1.1 Replace `components/Layout.tsx` and `components/SidebarNav.tsx` with the new shell: Overview ungrouped at the top, then Agents (Agents, Model providers), Work (Chat, Channels), Capabilities (MCP servers, Skills), Context (Knowledge, Memory), System (Secrets, Activity, Sync, Settings); no flag, the old components are deleted
- [ ] 1.2 Keep the experimental gate on Knowledge, Memory and Sync entries and the experimental marker, unchanged in behaviour; a group whose every entry is switched off renders no heading
- [ ] 1.3 Keep the collapsible icon rail and its `localStorage` memory, and the language switcher
- [ ] 1.4 Add the sidebar footer: connecting / running (with port) / stopping / offline from the existing status poll, desktop version warning through the credential-supplier module, click opens `/settings/daemon`, icon with tooltip on the collapsed rail
- [ ] 1.5 Generalise `useSyncAttention` into one attention-dot component and per-entry signal map; Sync keeps its seen-on-visit rule; an unreadable signal renders no dot

## 2. Routes

- [ ] 2.1 `router.tsx`: `/` renders the Overview page in place (no redirect to `/agents`); `/agents` unchanged
- [ ] 2.2 Settings routes `/settings/general`, `/settings/features`, `/settings/security`, `/settings/data`, `/settings/daemon`, `/settings/about`; `/settings` opens General
- [ ] 2.3 Model providers tabs: Providers (default) and Coffer's model at `?tab=coffer-model`; `/settings/engine` and `/settings/embedding` redirect to `/model-providers?tab=coffer-model`
- [ ] 2.4 `/secrets` route for the Secrets page
- [ ] 2.5 Agent detail tab routes (`?tab=` for Overview, Installed, Config files, Conversations, Memory, Model; Installed sections addressable); the old per-kind tab addresses (`?tab=skills`, `?tab=mcp-servers`, `?tab=plugins`) open the matching Installed section

## 3. Settings tabs

- [ ] 3.1 General: default page size and preferred editor only
- [ ] 3.2 Features: move the Experimental features card from General; the feature notice (`FeatureGate`) links to `/settings/features`
- [ ] 3.3 Daemon: status card, host-dependent restart (shell Restart control / `coffer daemon restart` to copy), read-only port with the CLI command, Start at login card moved from General, Rotate token with a confirmation that closes only on success and installs the returned token; loading skeleton and offline state
- [ ] 3.4 Move the engine page (`InternalEngineSettings`) under Model providers → Coffer's model
- [ ] 3.5 Data and About keep their contents; Security keeps only the master-key card (machine-level items); no stop or shutdown control anywhere

## 4. Secrets page

- [ ] 4.1 `pages/SecretsPage.tsx`: list from `GET /api/v1/credentials` with presence and used-by (kind and current name, each linking to the resource's page); shared table, loading, empty and error states
- [ ] 4.2 Add and replace through `POST /api/v1/credentials` (the value never shown back); Reveal behind an explicit action through the audited read; Delete behind a confirmation, refused while cited with the citers named (`409 CREDENTIAL_IN_USE`), the row kept
- [ ] 4.3 Leave a slot for the migration assistant entry and the unused marker; both arrive with the separate secrets change

## 5. Agent detail tabs

- [ ] 5.1 `pages/AgentDetailPage.tsx`: six tabs Overview, Installed, Config files, Conversations, Memory, Model
- [ ] 5.2 Installed tab: Skills, MCP servers and Plugins sections from `AgentSkillsTab`, `AgentMcpServersTab`, `AgentPluginsTab`, each row marked Coffer-managed or the agent's own; the Hooks section waits for the change that reads an agent's hooks
- [ ] 5.3 Config files tab lists the instructions files (`CLAUDE.md`, `AGENTS.md`) beside the settings files (already in the allowlist; check the grouping reads as one list)
- [ ] 5.4 Model tab: move the connection and model selection from `AgentOverviewTab`
- [ ] 5.5 Back links of `AgentMcpEntryPage`, `AgentPluginPage` and `UnmanagedSkillDetailPage` return to their Installed section

## 6. Command palette

- [ ] 6.1 Palette component opened by ⌘K / Ctrl+K and by a sidebar search control; Pages group from the sidebar entries and Settings tabs; Objects group from the agent list and each listed kind's list hook, matched by title and name
- [ ] 6.2 Navigation only — no entry that sends a mutating request; switched-off features' pages and objects left out
- [ ] 6.3 Per-group loading and error rows, Pages-only offline state, no-results message; arrow keys, Enter, Escape with focus return
- [ ] 6.4 en / zh strings for the palette, footer, Daemon and Features tabs, the Coffer's model tab label, the Secrets page and the agent detail tabs
- [ ] 6.5 i18n glossary: `nav.*` keys for the five group headings and thirteen entries, zh labels 总览 · 智能体（智能体、模型提供商）· 工作（聊天、消息渠道）· 能力（MCP 服务器、技能）· 上下文（知识、记忆）· 系统（密钥、活动、同步、设置）; replace every zh "Agent" naming an agent with 智能体 across `zh.json`; record the en/zh glossary in `.agents/frontend.md`; extend `i18n/surfaceNames.test.ts` to the new entries

## 7. Tests

- [ ] 7.1 `acceptance(web-ui, "the sidebar groups entries by what the user comes to do")` replaces "the sidebar groups agents, resources and system by role"; `acceptance(web-ui, "each listed resource kind has one sidebar entry")` replaces "resources holds one entry per kind with a list"; new `acceptance(web-ui, "a group with every entry switched off leaves the sidebar")`; `acceptance(web-ui, "a switched-off feature leaves the sidebar")` and "every resource entry opens a list page of its own" updated (`SidebarNav` tests); `acceptance(web-ui, "a surface carries one name in the sidebar and on its page")` updated for the glossary (`surfaceNames.test.ts`)
- [ ] 7.2 `acceptance(web-ui, "the index opens Overview")` replaces "the index opens the Agents page" (`router.test.tsx`)
- [ ] 7.3 `acceptance(web-ui, "cold-start renders authenticated content")` and `acceptance(web-ui, "daemon-offline banner appears when daemon is unreachable")` updated (`e2e/web/specs/shell_cold_start.spec.ts`)
- [ ] 7.4 `acceptance(web-ui, "settings layout uses the redesigned tabbed sidebar")` updated and `acceptance(web-ui, "settings offers no shutdown control")` replaces "settings drops the confusing controls" (`e2e/web/specs/shell_settings.spec.ts`); delete the marker for "settings shows no daemon tab and no daemon status" (`AboutPage.test.tsx`)
- [ ] 7.5 `acceptance(web-ui, "the settings daemon tab sets when the daemon runs")` replaces "the general tab sets when the daemon runs" (`DaemonResidencySettings.test.tsx`)
- [ ] 7.6 `acceptance(web-ui, …)` for "Coffer's model opens beside the providers" and "the old Coffer's model address redirects"
- [ ] 7.7 `acceptance(web-ui, …)` for the footer: "the footer shows a running daemon", "the footer says connecting before the first answer", "the footer shows an offline daemon", "the footer shows a stopping daemon", "the collapsed rail keeps the daemon state"
- [ ] 7.8 `acceptance(web-ui, …)` for the Daemon tab: "the settings daemon tab shows the running daemon", "the settings daemon tab offers the host's restart", "the settings daemon tab shows the port without editing it", "rotating the token from the settings daemon tab keeps the page working", "a failed rotation from the settings daemon tab keeps the old token", "the settings daemon tab keeps its layout while status loads", "the settings daemon tab with the daemon offline"
- [ ] 7.9 `acceptance(web-ui, …)` for the palette: "the palette jumps to a page", "the palette jumps to an object", "the palette offers no actions", "the palette leaves out switched-off features", "the palette lists pages while objects load", "a failing kind leaves the rest of the palette working", "the palette with the daemon offline", "the palette says when nothing matches"; one e2e spec for page and object jumps
- [ ] 7.10 `acceptance(web-ui, …)` for the dots: "an entry whose kind needs attention carries a dot", "the attention dot stays on the collapsed rail", "an entry without a signal never carries a dot", "an unreadable signal leaves no dot"
- [ ] 7.11 `acceptance(daemon, "the status probe carries what the shell shows")` on a daemon-route integration test beside the status tests
- [ ] 7.12 `acceptance(experimental-features, "the features tab switches a feature")` replaces "the general tab switches a feature" (`ExperimentalFeaturesSettings.test.tsx`); `acceptance(experimental-features, "a switched-off feature's page points at the Features tab")` on `FeatureGate.test.tsx`
- [ ] 7.13 `acceptance(internal-engine, "the Coffer's model tab shows and changes both halves")` replaces "Settings → Coffer's model shows and changes both halves" (`EngineSettings.test.tsx`)
- [ ] 7.14 `acceptance(desktop-app, "the shell hosts the one build the daemon serves")` updated for the Daemon tab and footer as sanctioned host-conditional places (`test_desktop_shell_surface.py`); the restart scenarios keep their names and markers
- [ ] 7.15 Migrate the e2e shell specs to role and label locators for the new sidebar
- [ ] 7.16 `acceptance(web-ui, …)` for "the security tab keeps only machine-level settings", "the secrets page lists each secret with what uses it", "a secret in use cannot be deleted from the secrets page" and "revealing a secret is an explicit, audited read"
- [ ] 7.17 `acceptance(agent-registry, "the agent detail page carries six tabs")` (`AgentDetailPage.test.tsx`); "open a plugin's detail page from the Plugins tab" and "open a direct MCP server's detail page from the agent" follow the Installed sections (`AgentPluginsTab`, `AgentPluginPage`, `AgentMcpEntryPage` tests); skill-manager "open an unmanaged skill's detail page from the agent's Skills tab" and "adopt or delete an unmanaged skill from its detail page" likewise (`AgentSkillsTab`, `UnmanagedSkillDetailPage` tests); provider-switching "the connections page lists profiles and their compatible agents" names the Model tab (`ModelProvidersPage.test.tsx`)

## 8. Docs

- [ ] 8.1 `docs-site/guides/web-ui.md`: the sidebar table with its five groups, Overview and Secrets, the six Settings tabs, the footer, Settings → Daemon, the command palette and attention dots; rotating the token is now in the UI, stopping stays CLI-only
- [ ] 8.2 `docs-site/guides/desktop-app.md`: Restart from Settings → Daemon, the footer's version warning, Start at login under Settings → Daemon
- [ ] 8.3 `docs-site/guides/daemon.md`, `experimental-features.md`, `providers.md`, `channels.md`, `knowledge.md`, `memory.md`, `vault-sync.md`, `troubleshooting.md`, `faq.md`, `start/*`, `reference/configuration.md`, `architecture/distribution.md`: Settings → General → Experimental features becomes Settings → Features; Settings → General → Coffer's daemon becomes Settings → Daemon; Settings → Coffer's model becomes Model providers → Coffer's model
- [ ] 8.4 `docs-site/guides/agents.md` (six detail tabs, Installed sections, Model tab), `credentials.md` (the Secrets page; Settings › Security machine-level), `providers.md` (Model providers under Agents; per-agent selection on the Model tab), `channels.md` (Channels under Work)
- [ ] 8.5 ADR [The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md): on acceptance set it Accepted, mark [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md) `Superseded by` it (or delete it if nothing it explains is inherited) and move both rows in the README index; ADR [Standalone Secrets Are Named `coffer://secret/` References](../../../docs/decisions/standalone-secrets-are-named-references-injected-into-one-child.md): "the Security page" lists stored secrets becomes the Secrets page; ADR [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md): follow the rename of "Leave daemon controls to the CLI"
- [ ] 8.6 Purpose sections: `web-ui` (grouped by what the user comes to do, Overview above the five groups; drop "grouped by role"), `credentials` (its visual surfaces are the Secrets page and Settings › Security, not Security alone), `desktop-app` (Restart control and skew warning rendered in the banner and on Settings → Daemon), `internal-engine` (Model providers → Coffer's model)
- [ ] 8.7 Code comments citing removed or renamed titles follow them (the list `scripts/check_spec_citations.py` prints): `useFeatures.ts`, `ExperimentalFeaturesSettings.tsx` and its test, `DaemonResidencySettings.tsx`, `InternalEngineSettings.tsx`
- [ ] 8.8 `.agents/frontend.md`: the palette, footer and attention-dot components as shell conventions, and the en/zh glossary (task 6.5)

## 9. Verify and archive

- [ ] 9.1 `make verify` (including spec citations, acceptance audit, OpenSpec strict validation, doc numbering, file sizes and codegen check)
- [ ] 9.2 Archive the change in the same PR as the shell implementation (`npx openspec archive revise-web-ui-ia --yes`)
