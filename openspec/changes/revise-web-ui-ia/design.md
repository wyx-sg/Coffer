## Context

The rebuild replaces the web UI's shell and pages in place, route by route. The information
architecture it implements is pinned by [web-ui](../../specs/web-ui/spec.md) and cited by the
ADR [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md), so it changes
here, as a contract, before the shell is written. The role grouping itself — Agents are the
consumers, Resources the assets, System the tooling — is unchanged; this change adds one entry
outside it, regroups Settings, makes the daemon visible and adds two navigation aids.

## Goals

- Fix the final navigation: entries, order, grouping and routes.
- Land on Overview.
- Make the daemon's state visible without making starting it the user's job.
- Regroup Settings by what each tab manages.
- Specify the command palette and attention dots at the level the shell needs.

Overview's own content is specified by a separate change, as are the Activity page's refresh
control and the new experimental switches for providers, chat and channels.

## Decisions

### 1. Final navigation

```
  Overview         /                        (ungrouped)
 AGENTS
  Agents           /agents
  Chat             /chat
 RESOURCES
  MCP servers      /mcp-servers
  Skills           /skills
  Knowledge        /knowledge               experimental: knowledge
  Memory           /memory                  experimental: memory
  Model providers  /model-providers         Providers | Coffer's model
  Channels         /channels
 SYSTEM
  Activity         /activity
  Sync             /sync                    experimental: vault_sync
  Settings         /settings                General | Features | Security | Data | Daemon | About
```

Overview sits above the groups under no heading. It summarises all three roles, so filing it under
any one misnames it. *Rejected:* a fourth "Home" group of one, which is a heading with nothing to
group; putting Overview under System, which reads as a system-health page rather than the landing
page.

The sidebar stays an honest inventory ("List only shipped surfaces in the sidebar"): no entry
carries a version label, and nothing is shown disabled.

### 2. Experimental switches hide entries — mechanism unchanged

An entry whose feature is off is left out of the sidebar, its routes render the feature notice,
and — new — its pages and objects are left out of the command palette. The registry, the order of
decision (pin, setting, channel) and the gates are those of
[experimental-features](../../specs/experimental-features/spec.md). Only the place a feature is
switched moves, from Settings → General to Settings → Features, and the notice links there. The
spec text names today's mapping (Knowledge, Memory, Sync); a change that adds a feature to the
registry adds its entry to that mapping and nothing else.

### 3. Landing route

`/` renders Overview in place; it is not a redirect to `/overview`. The landing page is the
product's front door and deserves the root address, and a redirect would put a second URL in the
history for the same page. `/agents` keeps its route; nothing that linked to it breaks. The
acceptance scenario "the index opens the Agents page" becomes "the index opens Overview".

### 4. Settings tab set

| Tab | Route | Holds |
| --- | --- | --- |
| General | `/settings/general` | Default page size, preferred external editor |
| Features | `/settings/features` | Experimental features card |
| Security | `/settings/security` | Master-key location |
| Data | `/settings/data` | Retention per log table, clear expired data |
| Daemon | `/settings/daemon` | Status, restart, port, Start at login, token rotation |
| About | `/settings/about` | Version, license, source |

- **Features gets its own tab** because it is a per-machine product decision rather than a display
  preference, and the rebuild's release channel starts with more features off; a card buried in
  General was the one place the user had to look to learn why a page was missing.
- **Start at login moves to Daemon.** It is the one daemon setting, and the Daemon tab is where a
  user looks for why the daemon was or was not running. *Rejected:* leaving it on General beside
  the display preferences, which splits the daemon across two tabs.
- **Coffer's model leaves Settings** for a tab on Model providers. It picks one of the providers
  listed there, and the curation and speech-to-text choices are provider choices; keeping it in
  Settings put a provider picker two sections away from the providers. *Rejected:* a Settings tab
  linking out to providers (two places to look), and a separate sidebar entry (a thirteenth entry
  for a page with three cards).
- The legacy `/settings/engine` redirects to `/model-providers?tab=coffer-model`, following the
  convention that a tab lives in `?tab=` and the default tab leaves it out.

### 5. Daemon visibility

The daemon was deliberately invisible ("Keep the daemon out of the user's view"): a healthy daemon
needs no readout and the offline banner owned the failure case. That left three gaps — "healthy"
and "not yet known" looked the same, the answering build and port were visible only in a terminal,
and the user had no in-app way to rotate a token or restart outside the offline case.

- **Footer.** The sidebar footer names one of four states — connecting, running (with its port),
  stopping, offline — and opens Settings → Daemon. It reads only the unauthenticated status probe,
  which the shell already polls for the offline banner, so it adds no route and no second poll.
  The footer and the banner must agree: the footer never reads running while the banner is up.
- **Settings → Daemon.** Status (from the probe), restart, port, Start at login and Rotate token.
  - *Restart is host-dependent.* In the desktop shell it is the shell's restart (the same IPC the
    tray and banner use). In a browser the tab shows `coffer daemon restart` to copy: a page the
    daemon serves cannot start the daemon that replaces it, and the login service restarts only
    on an unsuccessful exit. *Rejected:* a daemon self-restart route, which is new backend for a
    browser-only affordance and would still leave the page reconnecting blind.
  - *The port is shown, not edited.* [daemon](../../specs/daemon/spec.md) "Bind a fixed, settable
    port" keeps the port off REST because it is set when the daemon cannot bind; the tab shows the
    bound port and the CLI command beside it.
  - *Token rotation moves into the UI.* The route already exists and returns the new token, so the
    page installs it and continues without a reload. The confirmation names the consequence:
    other open pages recover on reload (the daemon injects the new token), the desktop shell
    re-handshakes from `daemon.json` on its next restart, and a client configured with a literal
    token stops working. *Rejected:* keeping rotation CLI-only, which the old rule justified as
    "needed maybe once ever"; with the daemon visible, a user who suspects a leaked token should
    not need a terminal to act on it.
  - *Stop stays CLI-only.* Stopping from the page kills the page, and recovery needs a terminal.
- **Starting stays automatic.** Every surface that needs a daemon still starts one; the footer
  and tab report state, they do not ask the user to act on a healthy system.

The desktop shell's sanctioned host-conditional affordances (Restart control, version-skew check)
are rendered in two places now — offline banner and Daemon tab — and the footer reads the skew
check's answer. They stay reached through the one credential-supplier module, so the frontend
still has no host branch outside it.

### 6. Command palette scope

⌘K / Ctrl+K, and a search control in the sidebar, open a palette that only navigates: pages
(every sidebar entry and Settings tab) and objects (agents and every listed resource kind,
matched by title and name). No actions. A palette that can also enable, delete or change reach is
a second way to reach every mutation, each needing its own confirmation and error handling, and it
bypasses the page that shows what the change will do. *Rejected:* an action palette in the style
of an editor's command list; it may come later as its own change.

The palette reads the list routes the pages already read and caches through the same query keys,
so opening it on a visited page costs nothing. Pages are static and always usable, so the palette
still works while the daemon is offline.

### 7. Sidebar attention dots

A dot, not a count, on the entry whose kind raises its attention signal, rendered by one shared
component and kept on the collapsed rail. The web UI owns only the rendering; what raises and
clears a signal belongs to the capability that owns the kind. Today there is one signal, Sync's
([vault-sync](../../specs/vault-sync/spec.md) "Say a vault needs a human where the user already
is"), which is cleared by visiting the page. The shared rule is extracted now because the shell is
being rewritten and the second user is already planned; each domain change that adds a signal
(for example an enabled MCP server that is unhealthy, a skill copy that has drifted, a channel
that needs attention) states its raise and clear rule in its own spec. An unreadable signal leaves
no dot: a sidebar that shows errors on every page is the floating banner the Sync dot replaced.

## Implementation notes

- **Settings contents gated until later work.** The tab set is final, but some contents arrive
  with later changes:
  - *Data regroup.* The Data tab carries retention and clear-expired-data now. Vault file
    locations, backup and export join it with the vault-files work; until then it holds only what
    ships. The plan's interim idea of parking retention on General is not taken: retention already
    ships and the Data tab exists, so moving it twice buys nothing.
  - *Secrets.* The Security tab carries the master-key location now. Credential management for
    skills and providers joins it with the models-and-secrets work.
- **Footer data.** Reuse the status poll behind `DaemonOfflineBanner`; do not add a second timer.
- **Palette data.** Reuse each kind's list hook; do not add an aggregate search route. A kind's
  list that is not cached is fetched on open.
- **Attention hook.** Generalise `useSyncAttention` into a per-entry signal map; Sync keeps its
  seen-key behaviour behind it.
- **Legacy redirects.** Keep `/settings/llm-connections`, `/settings/models`,
  `/settings/providers` and `/settings/embedding`; point `/settings/embedding` at the new Coffer's
  model address rather than at `/settings/engine`.

## Risks

- **Coffer's model behind a provider switch.** If a later change puts Model providers behind an
  experimental switch that is off on the stable channel, Coffer's model becomes unreachable in
  that build. That change must either keep the Coffer's model tab reachable or gate the engine's
  settings with it.
- **Token rotation strands other clients.** A second open tab or a client with a literal token
  fails until it re-reads the token. The confirmation says so; the offline banner already reads a
  `401` as "not ready" and a reload recovers a daemon-served page.
- **Acceptance markers.** Renamed scenarios break their markers until the tests follow; the tasks
  list each one.
