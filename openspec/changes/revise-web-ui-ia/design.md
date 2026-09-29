## Context

The rebuild replaces the web UI's shell and pages in place, route by route. The information
architecture it implements is pinned by [web-ui](../../specs/web-ui/spec.md) and cited by the
ADR [Sidebar Grouped by Role](../../../docs/decisions/sidebar-grouped-by-role.md), so it changes
here, as a contract, before the shell is written. This change replaces the role grouping with
five intent groups (argued in the Proposed ADR
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md)),
adds Overview and Secrets, regroups Settings and the agent detail page, makes the daemon visible
and adds two navigation aids.

## Goals

- Fix the final navigation: entries, order, grouping, routes and their names in both languages.
- Give stored secrets one page, and leave Settings › Security machine-level.
- Fix the agent detail page's tab set.
- Land on Overview.
- Make the daemon's state visible without making starting it the user's job.
- Regroup Settings by what each tab manages.
- Specify the command palette and attention dots at the level the shell needs.

Overview's own content is specified by a separate change, as are the Activity page's refresh
control, the new experimental switches for providers, chat and channels, the secrets behaviour
behind the Secrets page (uncited secrets, the migration assistant) and the read of an agent's
hooks.

## Decisions

### 1. Final navigation

```
  Overview         /                        (ungrouped)                 总览
 AGENTS                                                                智能体
  Agents           /agents                                              智能体
  Model providers  /model-providers         Providers | Coffer's model  模型提供商
 WORK                                                                  工作
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
  Sync             /sync                    experimental: vault_sync    同步
  Settings         /settings                General | Features | Security | Data | Daemon | About   设置
```

Thirteen entries. The grouping — by what the user comes to do, not by role — is argued in full,
against the role groups, one big Resources group, a flat list and fewer entries with tabs, in
[The Sidebar Is Grouped by What the Person Comes to Do](../../../docs/decisions/sidebar-grouped-by-what-the-person-comes-to-do.md).
The criterion it is measured by is that at the ~17 entries the roadmap names (Workflows in Work,
Rules and Sources in Capabilities, Usage in System) no group passes five; more agents, channels,
custom tools and ADE targets are rows inside existing pages. Rules is not in 1.0 — projecting
rules is deferred — so no Rules entry is specified here.

- **Chat and Channels stay two entries** in one group: Chat is daily conversation, Channels is
  occasional bot setup, and a channel's conversations already appear in Chat's list.
- **Model providers sits with Agents**: it is each agent's model configuration, chosen on the
  agent's Model tab; Coffer's model is a tab of it because it is a choice among the same
  connections.
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
| Security | `/settings/security` | Master-key location (machine-level items only) |
| Data | `/settings/data` | Retention per log table, clear expired data |
| Daemon | `/settings/daemon` | Status, restart, port, Start at login, token rotation |
| About | `/settings/about` | Version, license, source |

- **Features gets its own tab** because it is a per-machine product decision rather than a display
  preference, and the rebuild's release channel starts with more features off; a card buried in
  General was the one place the user had to look to learn why a page was missing.
- **Start at login moves to Daemon.** It is the one daemon setting, and the Daemon tab is where a
  user looks for why the daemon was or was not running. *Rejected:* leaving it on General beside
  the display preferences, which splits the daemon across two tabs.
- **Security becomes machine-level only.** It keeps the master-key location; stored secrets move
  to their own page (decision 8), because a secret is data the user manages, not a preference,
  and it is cited by resources of four kinds.
- **Coffer's model leaves Settings** for a tab on Model providers. It picks one of the providers
  listed there, and the curation and speech-to-text choices are provider choices; keeping it in
  Settings put a provider picker two sections away from the providers. *Rejected:* a Settings tab
  linking out to providers (two places to look), and a separate sidebar entry (a fourteenth entry
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

### 9. Agent detail tabs

| Tab | Holds |
| --- | --- |
| Overview | Identity, config directory, Coffer connection |
| Installed | Sections Skills, MCP servers, Plugins, Hooks — each row Coffer-managed or the agent's own |
| Config files | Every allowlisted file, instructions files (`CLAUDE.md`, `AGENTS.md`) included |
| Conversations | The agent's transcript sessions |
| Memory | The agent's native memory stores |
| Model | Connection and model selection (moved from Overview) |

Seven tabs become six. Skills, MCP servers and Plugins answered one question — what is installed
into this agent, and which of it Coffer manages — so they become sections of one tab, and Hooks
joins them there rather than as an eighth tab. Instructions files are configuration a person
wrote, not something installed, so they stay under Config files. The model choice leaves
Overview for its own tab so Overview is a summary rather than a form. Detail pages opened from a
section (a direct MCP entry, a plugin, an unmanaged skill) return to that section, so each
section is addressable in the URL.

The Hooks section needs a read of an agent's hooks that does not exist yet; it appears with the
change that adds it, and until then Installed has three sections ("List only shipped surfaces in
the sidebar" applies in spirit). *Rejected:* keeping per-kind tabs and adding Hooks and Model,
nine tabs, more than a tab strip shows at the page's width.

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
  `/settings/providers` and `/settings/embedding`; point `/settings/embedding` at the new Coffer's
  model address rather than at `/settings/engine`.

## Risks

- **Scenario names that name a tab.** OpenSpec cannot rename a scenario inside a MODIFIED
  requirement, so two scenarios keep names that mention a tab which is now a section:
  agent-registry "open a plugin's detail page from the Plugins tab" and skill-manager "open an
  unmanaged skill's detail page from the agent's Skills tab". Their bodies say "section of the
  Installed tab"; the names keep their acceptance markers stable.
- **Relearning the sidebar.** Users of the eleven-entry sidebar find Model providers under
  Agents and Channels under Work. The palette finds either by name, and routes are unchanged.

- **Coffer's model behind a provider switch.** If a later change puts Model providers behind an
  experimental switch that is off on the stable channel, Coffer's model becomes unreachable in
  that build. That change must either keep the Coffer's model tab reachable or gate the engine's
  settings with it.
- **Token rotation strands other clients.** A second open tab or a client with a literal token
  fails until it re-reads the token. The confirmation says so; the offline banner already reads a
  `401` as "not ready" and a reload recovers a daemon-served page.
- **Acceptance markers.** Renamed scenarios break their markers until the tests follow; the tasks
  list each one.
