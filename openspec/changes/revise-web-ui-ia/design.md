## Context

The rebuild replaces the web UI's shell and pages in place, route by route. The information
architecture it implements is pinned by [web-ui](../../specs/web-ui/spec.md) and cited by the
ADR [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md), so it changes
here, as a contract, before the shell is written. This change replaces the role grouping with
five intent groups (argued in the Proposed ADR
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)),
adds Overview, Secrets and Usage, moves Settings out of the sidebar into a modal and regroups
it, regroups the agent detail page, makes the daemon visible, adds two navigation aids, and
brings auto-update into the desktop shell.

## Goals

- Fix the final navigation: entries, order, grouping, routes and their names in both languages.
- Give stored secrets one page, and leave Settings › Security machine-level.
- Fix the agent detail page's tab set and the Agents list.
- Land on Overview.
- Make the daemon's state visible without making starting it the user's job.
- Regroup Settings by what each tab manages, and open it as a modal rather than a sidebar entry.
- Let the desktop app find and install its own updates.
- Specify the command palette and attention dots at the level the shell needs.

Overview's own content is specified by a separate change, as are the Activity page's refresh
control, the new experimental switches for providers, chat and channels, the secrets behaviour
behind the Secrets page (uncited secrets, the migration assistant).

## Decisions

### 1. Final navigation

```
  Overview         /                        (ungrouped)                 总览
 AGENTS                                                                智能体
  Agents           /agents                                              智能体
  Model providers  /model-providers                                     模型提供商
 RUN                                                                   运行
  Chat             /chat                                                聊天
  Channels         /channels                                            消息渠道
 CAPABILITIES                                                          能力
  MCP servers      /mcp-servers                                         MCP 服务器
  Skills           /skills                                              技能
 CONTEXT                                                               上下文
  Knowledge        /knowledge               experimental: knowledge     知识
  Memory           /memory                  experimental: memory        记忆
 SYSTEM                                                                系统
  Secrets          /secrets                                             密钥
  Activity         /activity                                            活动
  Usage            /usage                                               用量
  Sync             /sync                    experimental: vault_sync    同步
 ─────────────────────────────────────────────────────────────────────
  footer: daemon status · ⚙ Settings (modal)   /settings/<tab>          设置
```

Thirteen entries; Settings is not one of them (decision 4). Usage is in 1.0 — the page that shows
token use metered at the model proxy and the official remaining quota of subscription agents —
and its content is specified with the change that meters use; this change fixes only its place. The grouping — by what the user comes to do, not by role — is argued in full,
against the role groups, one big Resources group, a flat list and fewer entries with tabs, in
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).
The criterion it is measured by is that at the ~16 entries the roadmap names (Workflows in Run,
Rules and Sources in Capabilities) no group passes five; more agents, channels,
custom tools and ADE targets are rows inside existing pages. Rules is not in 1.0 — projecting
rules is deferred — so no Rules entry is specified here.

- **Chat and Channels stay two entries** in one group: Chat is daily conversation, Channels is
  occasional bot setup, and a channel's conversations already appear in Chat's list.
- **Model providers sits with Agents**: it is each agent's model configuration, chosen on the
  agent's Model tab. The page is one table of connections; which agent runs on a connection is
  read on that connection's detail page (Used by, read-only) and changed only on the agent's
  Model tab, so there is one place to switch.
- **Secrets sits in System**: it is shared infrastructure data cited by MCP servers, providers,
  skills and channels (decision 8).
- **A group with no entry left hides its heading** — switching off both Knowledge and Memory
  leaves no Context heading. *Rejected:* keeping an empty heading, which is the "soon"
  placeholder the sidebar rules out.
- **Routes do not move.** Only headings and order change, so no redirect is needed.

Overview sits above the groups under no heading. It summarises all five, so filing it under any
one misnames it. *Rejected:* a "Home" group of one, which is a heading with nothing to group;
putting Overview under System, which reads as a system-health page rather than the landing page.

The sidebar stays an honest inventory ("List only shipped surfaces in the sidebar"): no entry
carries a version label, and nothing is shown disabled.

**Names.** One name per surface in both languages ("Call a surface by one name everywhere"),
now with the whole zh glossary in the requirement: in Chinese an agent is 智能体 everywhere,
replacing today's "Agent" in `zh.json`. The palette, page headers and dialogs read the same keys
as the sidebar.

### 2. Experimental switches hide entries — mechanism unchanged

An entry whose feature is off is left out of the sidebar, its routes render the feature notice,
and — new — its pages and objects are left out of the command palette. The registry, the order of
decision (pin, setting, channel) and the gates are those of
[experimental-features](../../specs/experimental-features/spec.md). The notice says the feature
is off and links to no Settings tab, because Settings no longer lists features (decision 4). The
spec text names today's mapping (Knowledge, Memory, Sync); a change that adds a feature to the
registry adds its entry to that mapping and nothing else.

### 3. Landing route

`/` renders Overview in place; it is not a redirect to `/overview`. The landing page is the
product's front door and deserves the root address, and a redirect would put a second URL in the
history for the same page. `/agents` keeps its route; nothing that linked to it breaks. The
acceptance scenario "the index opens the Agents page" becomes "the index opens Overview".

### 4. Settings: a modal, and its tab set

**Settings leaves the sidebar.** A gear at the bottom of the sidebar, beside the daemon status,
and ⌘, (Ctrl+, elsewhere) open Settings as a large modal over the current page; the footer's
daemon state opens it on Daemon. Settings is visited rarely and is about this machine, not about
the vault's contents, so an entry for it sat in System beside pages used every week; desktop
applications keep their preferences in a window of their own (macOS apps' Settings under ⌘,,
VS Code, Linear), and a user reaching for ⌘, finds it where they expect. *Rejected:* keeping
Settings as the last System entry, which spends a sidebar row on a page opened a few times a
year and, with Usage in 1.0, would already fill System to five, the ceiling the grouping allows.

**It stays addressable.** Each tab keeps `/settings/<tab>`. The router renders the modal over a
background location: opening it from a page keeps that page mounted underneath, and closing it
(close control, Escape, click outside, or Back) returns to that page's route. A fresh load of a
Settings route, with no page underneath, renders the modal over Overview and closes to `/`. Deep
links (the footer's `/settings/daemon`) and the
palette's Settings tabs therefore all open the same modal. This routing is the cost of the modal:
a Settings page was one route per tab, a modal over a background location needs the router to
carry the page underneath. *Rejected:* a modal with no route, which would break every deep link
and the palette's Settings tabs; and a separate window in the desktop shell, which a browser host
cannot have.

| Tab | Route | Holds |
| --- | --- | --- |
| General | `/settings/general` | Default page size, preferred external editor |
| Security | `/settings/security` | Master-key location (machine-level items only) |
| Data | `/settings/data` | Retention per log table, clear expired data |
| Daemon | `/settings/daemon` | Status, restart, port, Start at login, token rotation |
| About | `/settings/about` | Version, license, source, update check (desktop shell) |

- **No Features tab.** At 1.0 every experimental feature graduates and its switch code is
  deleted, so a Features tab would be empty; the Experimental features card leaves General with
  nothing in its place. *Rejected:* a Features tab kept for later flags, which is the empty
  placeholder the sidebar rules already refuse.
- **Start at login moves to Daemon.** It is the one daemon setting, and the Daemon tab is where a
  user looks for why the daemon was or was not running. *Rejected:* leaving it on General beside
  the display preferences, which splits the daemon across two tabs.
- **Security becomes machine-level only.** It keeps the master-key location; stored secrets move
  to their own page (decision 8), because a secret is data the user manages, not a preference,
  and it is cited by resources of four kinds.
- **Coffer's model is a section of General.** It configures Coffer itself — the model its own
  engine runs on and the speech-to-text model — which is machine-level configuration like the
  rest of Settings, not an agent's model. Two pickers, each choosing a provider and then a model
  from that provider's list, bring the provider choice to where it is needed, so it does not
  have to sit beside the provider table; a Test action and inline not-set / failing states say
  whether the pair works without a trip to Activity. The call bound sits beside the engine picker
  and the upkeep passes below the pickers. *Rejected:* a Coffer's model tab on Model providers,
  which made the provider page carry Coffer's configuration beside the agents'; and a separate
  Settings tab, one more tab for two pickers.
- **Model providers loses its tabs.** A "who runs on what" view repeated what each agent's Model
  tab shows and offered a second place to switch. It is dropped: a provider's detail page lists
  its users read-only, each linking to where it is changed.
- The legacy `/settings/engine` opens the Settings modal on General.

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

### 8. Secrets page

`/secrets` lists every secret the store reports, with presence and what uses it (kind and
current name, each a link), and carries add, replace, reveal and delete. Reveal is an explicit
action and an audited read; delete is refused while any resource cites the secret, naming the
citers, as the credential routes already do. The entry to the migration assistant (plaintext
secret files into the store) appears when that assistant ships.

The page is specified at the level of place and parts only. A separate secrets change owns what
the store enumerates beyond cited references (so that unused secrets can be listed), the
migration assistant, and any new route; until it lands the page reads `GET /api/v1/credentials`
and the existing value, store and delete routes, and "unused" can only be shown once uncited
secrets are enumerated. *Rejected:* growing Settings › Security into the secrets list (the plan's
earlier idea), which puts shared data among machine preferences and hides it one level down;
and a secrets section on each kind's page, which leaves every page blind to the other kinds that
cite the same key. A secret field in a resource's own dialog stays: a secret is entered where the
thing that needs it is configured.

### 9. Agent detail tabs and the Agents list

| Tab | Path | Holds |
| --- | --- | --- |
| Overview | `/agents/<type>` | Type, config directory, Coffer connection; one summary row each for Skills, MCP servers, Plugins, Hooks, opening its tab |
| Model | `…/model` | Connection and model selection (moved from Overview); the only place an agent's provider is switched |
| Skills | `…/skills` | Coffer's skills and the agent's own; Adopt, Remove duplicate |
| MCP servers | `…/mcp-servers` | Coffer's servers and direct entries; Adopt, Remove duplicate |
| Plugins | `…/plugins` | Installed plugins; enable, disable, Uninstall |
| Hooks | `…/hooks` | Hooks the agent's configuration declares, Coffer's marked; Open file |
| Config files | `…/config` | Every allowlisted file, instructions files (`CLAUDE.md`, `AGENTS.md`) included |
| Memory | `…/memory` | The agent's native memory stores |
| Conversations | `…/conversations` | The agent's transcript sessions |

Nine tabs, one per kind of thing an agent holds. Each installed-kind tab lists Coffer's entries
and the agent's own in one table with one owner filter (All / Coffer / the agent's own), so
"what does this agent have" and "what of it does Coffer manage" are the same table read two
ways, and each kind keeps the actions only it has. Overview is a summary whose rows open those
tabs, and carries no Title or Name: an agent's name is fixed to its type. Model comes second
because it is the most common reason to open an agent. Each tab has its own path, and detail
pages opened from a tab (a direct MCP entry, a plugin, an unmanaged skill) return to it.
*Rejected:* one Installed tab with a section per kind, which put four tables with different
actions on one scrolling page and hid the Hooks table below three others.

The Hooks tab reads the hooks listing that already ships (agent-registry "List every hook in the
agent's native config"), so all nine tabs are in 1.0.

**The Agents list is two fixed rows** — Claude Code and Codex, the supported types — found
automatically each time the page loads. A row is not installed (with the install command to
copy), config left behind with its program not found (with the reinstall command), not added
(Add) — including installed but never run, whose config directory Add creates with only Coffer's
entries — or added with its Coffer state (Connect, Repair). Add registers the agent under its
default config directory and connects it; feature/rearch's rule that only `installed_active`
can be added is relaxed for `installed_never_run`, because a first-run user who has installed
Codex but not opened it yet should not have to run it once before Coffer can set it up; Add, Connect and Repair each preview every
file they will write before writing. A different config directory is the exception, so it is a
row-menu item. First run, with neither added, offers Add both. *Rejected:* a Detect agents button
and an Add agent dialog with type, name and title fields — the types are fixed, detection is
cheap enough to run on every load, and a name the user types for an agent whose type already
names it is one more thing to get wrong.

### 11. Adding an MCP server

One **Add server** action replaces the separate paste-JSON button. Its dialog opens on a paste box
that recognises the forms a README hands out — an `mcpServers` block or one server object, Codex
TOML `[mcp_servers.<name>]` tables, a command line (`claude mcp add …`, `codex mcp add …` or a
plain `npx …`), or a URL — so the user never picks a format before pasting. One server opens the
manual form prefilled, because a single server is easiest to check field by field; several open
the existing review step, where secrets move to the credential store, names are normalised and can
be corrected before they become fixed, and reach is chosen. Unreadable input says what it accepts
and offers the manual type choice rather than a dead end. Import from agents stays a link in the
same dialog, not a second page action. *Rejected:* a format picker before the paste box, which
asks the user a question the text already answers. This is a web UI form over
[mcp-gateway](../../specs/mcp-gateway/spec.md) registration, so the requirements are web-ui's;
the gateway's registration rules (fixed names, the 24-character limit) are unchanged.

### 10. Auto-update

A new version reached a desktop user only if they downloaded a new `.dmg`, and the desktop spec
listed auto-update as out of scope. It is now in scope for 1.0. The shell checks at launch and
every six hours through the Tauri updater against a manifest the release workflow publishes on
GitHub Releases, and Settings › About shows the running version, the last check, a Check for
updates control and, when a newer version exists, Download and restart.

- **Signed, and verified by the shell.** The updater archive is signed with an updater key held
  as a repository secret; the shell carries the public key and refuses anything that does not
  verify. GitHub Releases is only transport, so a compromised release page cannot push code.
- **The user installs; the timer only checks.** A background check records its result for About
  and never interrupts. *Rejected:* installing silently on quit, which changes a running tool
  under the user without a word, and a system notification per release, which a six-hour timer
  would repeat.
- **The daemon follows the app.** After the relaunch the skew check sees the previous version's
  daemon and the shell replaces it through the one restart, so no second restart path exists.
- **The check runs in the shell, not the webview**, so the content policy stays loopback and IPC.
- **In a browser, About shows the version only**: a page the daemon serves cannot replace the
  application, and the terminal tier updates by reinstalling its archive.

The update check is a third sanctioned host affordance, reached through the same
credential-supplier module as Restart and the skew check and rendered only on About.

## Implementation notes

- **Settings contents gated until later work.** The tab set is final, but some contents arrive
  with later changes:
  - *Data regroup.* The Data tab carries retention and clear-expired-data now. Vault file
    locations, backup and export join it with the vault-files work; until then it holds only what
    ships. The plan's interim idea of parking retention on General is not taken: retention already
    ships and the Data tab exists, so moving it twice buys nothing.
  - *Secrets.* The Security tab carries the master-key location only. Credential management
    lives on the Secrets page (decision 8), whose deeper behaviour arrives with the secrets
    change.
- **Footer data.** Reuse the status poll behind `DaemonOfflineBanner`; do not add a second timer.
- **Palette data.** Reuse each kind's list hook; do not add an aggregate search route. A kind's
  list that is not cached is fetched on open.
- **Attention hook.** Generalise `useSyncAttention` into a per-entry signal map; Sync keeps its
  seen-key behaviour behind it.
- **Legacy redirects.** Keep `/settings/llm-connections`, `/settings/models`,
  `/settings/providers` and `/settings/embedding`; point `/settings/engine` and
  `/settings/embedding` at `/settings/general`. `/settings/embedding` is an existing redirect
  for old bookmarks only — Coffer has no embedding configuration — and no new Settings route is
  added for speech to text, which is a picker in General.

## Risks

- **A scenario name that no longer matches its body.** agent-registry "show a leftover config
  directory as not installed" keeps its name because OpenSpec refuses to drop a scenario from a
  MODIFIED requirement; its body says the row reads as config left behind, program not found.
- **The registry still allows more than a row per type.** Agents keep a renamable name, a title
  and, per type, any number of config directories ("Manage the agent lifecycle", "Allow one agent
  per name and per config directory"). The Agents list and the `/agents/<type>` paths assume one
  agent per type named by its type; the change that narrows the registry to that owns the
  backend and CLI side, and until it lands the web UI shows the first agent of each type.
- **Relearning the sidebar.** Users of the eleven-entry sidebar find Model providers under
  Agents, Channels under Run, and Settings behind the footer gear. The palette finds each by
  name, and routes are unchanged.
- **Auto-update depends on signing.** A replaced `.app` must keep its identity for Gatekeeper
  and the keychain, so the updater is built after the release is Apple Developer ID signed;
  the tasks order it that way.
- **Losing the updater key strands every install.** The public key is built into each shipped
  shell, so a lost private key means no update can be verified; the key is kept in the
  repository's secrets with an offline backup.

- **Token rotation strands other clients.** A second open tab or a client with a literal token
  fails until it re-reads the token. The confirmation says so; the offline banner already reads a
  `401` as "not ready" and a reload recovers a daemon-served page.
- **Acceptance markers.** Renamed scenarios break their markers until the tests follow; the tasks
  list each one.
