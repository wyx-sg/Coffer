## Why

The web UI is being rebuilt in place: a new shell, a new design system and new pages for each
domain. Before any of that lands, the information architecture it implements has to be the
contract, because the current specs pin the old one — eleven sidebar entries, an index that
redirects to Agents, five Settings tabs, and a daemon the user is never shown.

Four decisions change that architecture:

- **A landing page.** Opening the app should show the whole vault — what is healthy and what
  needs the user — before any one part of it. Landing on Agents shows one kind and hides the rest.
- **The daemon made visible.** Hiding the daemon left a user unable to tell "healthy" from "not
  yet known", or to see which build and port are answering and whether it starts at login, without
  a terminal. The daemon's state becomes visible at all times; starting it stays automatic.
- **Settings regrouped.** Experimental features get their own tab, the daemon gets one, and
  Coffer's own model moves beside the providers it is chosen from.
- **A command palette and attention dots.** With twelve entries and many objects, the user needs
  one keystroke to reach any page or object, and one mark on the entry that needs them.

This change is the contract step. It ships together with the shell implementation, so it stays
unarchived until that implementation lands.

## What Changes

- The sidebar gains an ungrouped **Overview** entry above the Agents, Resources and System groups;
  the entry set becomes twelve. Experimental switches hide entries exactly as before.
- `/` renders the Overview page in place instead of redirecting to `/agents`. Overview's content
  is specified separately.
- Settings has six tabs: **General, Features, Security, Data, Daemon, About**. Experimental
  features move from General to Features; the Start at login card moves from General to Daemon.
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
- `web-ui`: the sidebar entry set and grouping (Overview added), landing on Overview, six Settings
  tabs, Coffer's model beside Model providers, the daemon footer and Settings → Daemon, the command
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

## Impact

- Frontend: `components/Layout.tsx`, `components/SidebarNav.tsx` (replaced), a new sidebar footer
  and command palette, `router.tsx` (index route, `/settings/*` tabs, `/settings/engine` redirect,
  Model providers tabs), `pages/settings/*` (Features and Daemon tabs, residency card moved),
  `pages/ModelProvidersPage.tsx`, the attention-dot hook generalised from `useSyncAttention`, i18n
  strings in both locales.
- Desktop: no Rust change; the frontend's credential-supplier module exposes the restart and skew
  check to the Daemon tab and footer.
- Backend and contracts: none; every screen reads routes that already exist
  (`/daemon/status`, `/daemon/residency`, `/daemon/rotate-token`, `/daemon/features`, the kind list
  routes).
- Tests: web-ui, experimental-features, internal-engine and desktop-app acceptance markers for the
  new and renamed scenarios; e2e shell specs (`shell_cold_start`, `shell_settings`) and new ones
  for the palette, footer and Daemon tab.
- Docs: docs-site guides (`web-ui`, `desktop-app`, `daemon`, `experimental-features`,
  `providers`, and the pages naming Settings → General or Settings → Coffer's model), the ADR
  [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md) and the ADR
  [Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md)
  that cite renamed requirements, and the Purpose sections of `web-ui`, `desktop-app` and
  `internal-engine`.
