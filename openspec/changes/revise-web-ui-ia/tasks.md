## 1. Shell layout and sidebar

- [ ] 1.1 Replace `components/Layout.tsx` and `components/SidebarNav.tsx` with the new shell: Overview ungrouped at the top, then Agents (Agents, Chat), Resources (MCP servers, Skills, Knowledge, Memory, Model providers, Channels), System (Activity, Sync, Settings); no flag, the old components are deleted
- [ ] 1.2 Keep the experimental gate on Knowledge, Memory and Sync entries and the experimental marker, unchanged in behaviour
- [ ] 1.3 Keep the collapsible icon rail and its `localStorage` memory, and the language switcher
- [ ] 1.4 Add the sidebar footer: connecting / running (with port) / stopping / offline from the existing status poll, desktop version warning through the credential-supplier module, click opens `/settings/daemon`, icon with tooltip on the collapsed rail
- [ ] 1.5 Generalise `useSyncAttention` into one attention-dot component and per-entry signal map; Sync keeps its seen-on-visit rule; an unreadable signal renders no dot

## 2. Routes

- [ ] 2.1 `router.tsx`: `/` renders the Overview page in place (no redirect to `/agents`); `/agents` unchanged
- [ ] 2.2 Settings routes `/settings/general`, `/settings/features`, `/settings/security`, `/settings/data`, `/settings/daemon`, `/settings/about`; `/settings` opens General
- [ ] 2.3 Model providers tabs: Providers (default) and Coffer's model at `?tab=coffer-model`; `/settings/engine` and `/settings/embedding` redirect to `/model-providers?tab=coffer-model`

## 3. Settings tabs

- [ ] 3.1 General: default page size and preferred editor only
- [ ] 3.2 Features: move the Experimental features card from General; the feature notice (`FeatureGate`) links to `/settings/features`
- [ ] 3.3 Daemon: status card, host-dependent restart (shell Restart control / `coffer daemon restart` to copy), read-only port with the CLI command, Start at login card moved from General, Rotate token with a confirmation that closes only on success and installs the returned token; loading skeleton and offline state
- [ ] 3.4 Move the engine page (`InternalEngineSettings`) under Model providers → Coffer's model
- [ ] 3.5 Security, Data and About keep their contents; no stop or shutdown control anywhere

## 4. Command palette

- [ ] 4.1 Palette component opened by ⌘K / Ctrl+K and by a sidebar search control; Pages group from the sidebar entries and Settings tabs; Objects group from the agent list and each listed kind's list hook, matched by title and name
- [ ] 4.2 Navigation only — no entry that sends a mutating request; switched-off features' pages and objects left out
- [ ] 4.3 Per-group loading and error rows, Pages-only offline state, no-results message; arrow keys, Enter, Escape with focus return
- [ ] 4.4 en / zh strings for the palette, footer, Daemon and Features tabs, and the Coffer's model tab label

## 5. Tests

- [ ] 5.1 `acceptance(web-ui, "the sidebar groups agents, resources and system by role")` and `acceptance(web-ui, "a switched-off feature leaves the sidebar")` updated for Overview (`SidebarNav` tests)
- [ ] 5.2 `acceptance(web-ui, "the index opens Overview")` replaces "the index opens the Agents page" (`router.test.tsx`)
- [ ] 5.3 `acceptance(web-ui, "cold-start renders authenticated content")` and `acceptance(web-ui, "daemon-offline banner appears when daemon is unreachable")` updated (`e2e/web/specs/shell_cold_start.spec.ts`)
- [ ] 5.4 `acceptance(web-ui, "settings layout uses the redesigned tabbed sidebar")` updated and `acceptance(web-ui, "settings offers no shutdown control")` replaces "settings drops the confusing controls" (`e2e/web/specs/shell_settings.spec.ts`); delete the marker for "settings shows no daemon tab and no daemon status" (`AboutPage.test.tsx`)
- [ ] 5.5 `acceptance(web-ui, "the settings daemon tab sets when the daemon runs")` replaces "the general tab sets when the daemon runs" (`DaemonResidencySettings.test.tsx`)
- [ ] 5.6 `acceptance(web-ui, …)` for "Coffer's model opens beside the providers" and "the old Coffer's model address redirects"
- [ ] 5.7 `acceptance(web-ui, …)` for the footer: "the footer shows a running daemon", "the footer says connecting before the first answer", "the footer shows an offline daemon", "the footer shows a stopping daemon", "the collapsed rail keeps the daemon state"
- [ ] 5.8 `acceptance(web-ui, …)` for the Daemon tab: "the settings daemon tab shows the running daemon", "the settings daemon tab offers the host's restart", "the settings daemon tab shows the port without editing it", "rotating the token from the settings daemon tab keeps the page working", "a failed rotation from the settings daemon tab keeps the old token", "the settings daemon tab keeps its layout while status loads", "the settings daemon tab with the daemon offline"
- [ ] 5.9 `acceptance(web-ui, …)` for the palette: "the palette jumps to a page", "the palette jumps to an object", "the palette offers no actions", "the palette leaves out switched-off features", "the palette lists pages while objects load", "a failing kind leaves the rest of the palette working", "the palette with the daemon offline", "the palette says when nothing matches"; one e2e spec for page and object jumps
- [ ] 5.10 `acceptance(web-ui, …)` for the dots: "an entry whose kind needs attention carries a dot", "the attention dot stays on the collapsed rail", "an entry without a signal never carries a dot", "an unreadable signal leaves no dot"
- [ ] 5.11 `acceptance(daemon, "the status probe carries what the shell shows")` on a daemon-route integration test beside the status tests
- [ ] 5.12 `acceptance(experimental-features, "the features tab switches a feature")` replaces "the general tab switches a feature" (`ExperimentalFeaturesSettings.test.tsx`); `acceptance(experimental-features, "a switched-off feature's page points at the Features tab")` on `FeatureGate.test.tsx`
- [ ] 5.13 `acceptance(internal-engine, "the Coffer's model tab shows and changes both halves")` replaces "Settings → Coffer's model shows and changes both halves" (`EngineSettings.test.tsx`)
- [ ] 5.14 `acceptance(desktop-app, "the shell hosts the one build the daemon serves")` updated for the Daemon tab and footer as sanctioned host-conditional places (`test_desktop_shell_surface.py`); the restart scenarios keep their names and markers
- [ ] 5.15 Migrate the e2e shell specs to role and label locators for the new sidebar

## 6. Docs

- [ ] 6.1 `docs-site/guides/web-ui.md`: the sidebar table with Overview, the six Settings tabs, the footer, Settings → Daemon, the command palette and attention dots; rotating the token is now in the UI, stopping stays CLI-only
- [ ] 6.2 `docs-site/guides/desktop-app.md`: Restart from Settings → Daemon, the footer's version warning, Start at login under Settings → Daemon
- [ ] 6.3 `docs-site/guides/daemon.md`, `experimental-features.md`, `providers.md`, `channels.md`, `knowledge.md`, `memory.md`, `vault-sync.md`, `troubleshooting.md`, `faq.md`, `start/*`, `reference/configuration.md`, `architecture/distribution.md`: Settings → General → Experimental features becomes Settings → Features; Settings → General → Coffer's daemon becomes Settings → Daemon; Settings → Coffer's model becomes Model providers → Coffer's model
- [ ] 6.4 ADR [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md): amend for the ungrouped Overview entry and cite "Keep the sidebar to its twelve entries"; ADR [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md): follow the rename of "Leave daemon controls to the CLI"
- [ ] 6.5 Purpose sections: `web-ui` (Overview outside the three roles), `desktop-app` (Restart control and skew warning rendered in the banner and on Settings → Daemon), `internal-engine` (Model providers → Coffer's model)
- [ ] 6.6 Code comments citing removed or renamed titles follow them (the list `scripts/check_spec_citations.py` prints): `useFeatures.ts`, `ExperimentalFeaturesSettings.tsx` and its test, `DaemonResidencySettings.tsx`, `InternalEngineSettings.tsx`
- [ ] 6.7 `.agents/frontend.md`: the palette, footer and attention-dot components as shell conventions

## 7. Verify and archive

- [ ] 7.1 `make verify` (including spec citations, acceptance audit, OpenSpec strict validation, doc numbering, file sizes and codegen check)
- [ ] 7.2 Archive the change in the same PR as the shell implementation (`npx openspec archive revise-web-ui-ia --yes`)
