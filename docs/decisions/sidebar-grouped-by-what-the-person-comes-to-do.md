# The Sidebar Is Grouped by What the Person Comes to Do: Agents, Run, Capabilities, Context, System

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: supersedes [The Sidebar Is Grouped by Role: Agents, Resources, System](sidebar-grouped-by-role.md) once accepted,
[Resource Framework Upfront](resource-framework-upfront.md),
[Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md),
[LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md),
[The Engine Owns Its Model; Its Endpoint Is Borrowed From a Flagged Connection](internal-engine-settings.md),
[Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md),
[Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon](channel-adapter-framework.md),
[Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md),
[Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md),
spec web-ui "Group the sidebar by what the user comes to do",
spec web-ui "Keep the sidebar to its thirteen entries",
spec web-ui "Give each listed resource kind one sidebar entry",
spec web-ui "List only shipped surfaces in the sidebar",
spec web-ui "Call a surface by one name everywhere",
spec web-ui "Manage stored secrets on the Secrets page",
spec web-ui "Open Settings as a modal from the sidebar footer",
spec chat "Show every conversation on the Chat page",
spec provider-switching "Offer every connection operation on REST, CLI and web",
spec credentials "Refuse to delete a credential still in use",
the change `openspec/changes/revise-web-ui-ia/`

## Context

The sidebar today holds eleven entries in three role groups — Agents (Agents, Chat), Resources
(MCP servers, Skills, Knowledge, Memory, Model providers, Channels), System (Activity, Sync,
Settings) — decided in [The Sidebar Is Grouped by Role](sidebar-grouped-by-role.md). The role
axis was chosen so that "a new asset kind is one more Resources row and never a new group".

The rebuild makes that promise expensive. Three entries arrive with it: **Overview**, the landing
page; **Secrets**, a page that lists every stored secret with what uses it, which the
credential store has never had
([Standalone Secrets Are Named `coffer://secret/` References](standalone-secrets-are-named-references-injected-into-one-child.md)
makes every stored secret listable with its reference count); and **Usage**, token use metered
at the model proxy and the official remaining quota of subscription agents, which is in 1.0.
One entry leaves: **Settings** becomes a modal opened from the sidebar footer (argued below).
That is thirteen. The roadmap after 1.0 already names three more entries, and several additions
that must *not* become entries:

| Future addition | Lands as |
| --- | --- |
| Workflows, with a Workflows tab and a Runs tab; scheduled tasks are workflows with a schedule trigger | one entry |
| Rules (instructions projected into each agent's instruction files) | one entry |
| Sources (read-only git sources a vault subscribes to, for skills and the like) | one entry |
| Custom tools (`script`, `http` and `openapi` transports of an MCP server) | rows on MCP servers |
| More agents; agentic development environments (ADEs) as delivery targets | rows on Agents |
| More channels (IM transports) | rows on Channels |

So the navigation has to hold about **sixteen entries** without being regrouped, and every
kind of growth that is "more of the same" has to land inside a page. The criterion every option
below is measured against: **at ~16 entries, no group grows past ~5**. Five is where a group
heading still reads as one idea at a glance; past it, a group becomes a list the eye scans row by
row, which is what grouping was meant to avoid.

Rules is not in 1.0: projecting rules into each agent's instruction files is deferred, and no
entry ships before its feature (web-ui "List only shipped surfaces in the sidebar"). It is
counted here because the grouping must already have room for it.

Four placement questions have to be answered by whatever grouping wins, because each was
contested while the rebuild was designed:

- **Chat and Channels.** Both put a person in a conversation with an agent; should they be one
  entry?
- **Model providers.** Is a provider an asset like an MCP server, a setting, or part of setting
  up an agent?
- **Secrets.** A secret is cited by MCP servers, model providers, channels and skills; where does
  a page for all of them go, and what stays on Settings › Security?
- **Settings.** Is Settings a sidebar entry at all?

## Options Considered

Entry counts below are *1.0* (13, with Overview, Secrets and Usage, and Settings as a modal) →
*at ~16* (with Workflows, Rules and Sources). Overview is ungrouped in every option, for the
reason given under the Decision, and Settings is a modal in every option, for the reason given
under the placement questions.

### Option A — role groups, as today: Agents, Resources, System

Keep [The Sidebar Is Grouped by Role](sidebar-grouped-by-role.md) and add the new entries where
its rule puts them: Secrets as the last Resources row (a credentialed asset), Usage under
System, Workflows under Agents (a thing done with agents), Rules and Sources under Resources.

| Group | 1.0 | At ~16 |
| --- | --- | --- |
| Agents | Agents, Chat (2) | + Workflows (3) |
| Resources | MCP servers, Skills, Knowledge, Memory, Model providers, Channels, Secrets (7) | + Rules, Sources (9) |
| System | Activity, Usage, Sync (3) | 3 |

Pros: no migration of the user's mental map; the rule that places an entry is one question
("consumer, asset or tooling?") and has never been hard to answer. Cons: it fails the criterion
already at 1.0 — seven Resources rows — and reaches nine, more than half the sidebar under one
heading. "Resource" is the framework's word, not the user's: nobody comes to Coffer to "manage
resources"; they come to give an agent a tool, to tell it something, or to wire up a bot. The
role axis also puts Channels, a bot the user sets up occasionally, between Model providers and
Secrets rather than beside Chat, the page where its conversations show up. **Loses** on the
criterion; the one-big-group shape is exactly what the other options try to fix.

### Option B — intent groups for the verbs, one Resources group for the nouns

Group what the user *does* by intent — a Run group (Chat, Channels, later Workflows) and System
— and keep one Resources group for everything that is configured: Agents, Model providers, MCP
servers, Skills, Knowledge, Memory, Secrets.

| Group | 1.0 | At ~16 |
| --- | --- | --- |
| Run | Chat, Channels (2) | + Workflows (3) |
| Resources | Agents, Model providers, MCP servers, Skills, Knowledge, Memory, Secrets (7) | + Rules, Sources (9) |
| System | Activity, Usage, Sync (3) | 3 |

Pros: Chat and Channels sit together, where a user looks for "talking to an agent"; three
headings stay easy to learn. Cons: it moves the problem rather than solving it — Resources is
still seven, then nine — and it puts Agents, the subject of the whole product, in the middle of
a list of the things agents use, the mislabelling the role ADR rejected as its own Option B.
**Loses** on the criterion for the same reason as A.

### Option C' — five intent groups: Agents, Run, Capabilities, Context, System (chosen)

Split the configured nouns by what the user comes to do with them, so every group is one
intent:

| Group | What the user comes to do | 1.0 | At ~16 |
| --- | --- | --- | --- |
| Agents | set up the agents and the models they run on | Agents, Model providers (2) | 2 |
| Run | put an agent to work, directly or through an IM bot | Chat, Channels (2) | + Workflows (3) |
| Capabilities | give agents things they can do | MCP servers, Skills (2) | + Rules, Sources (4) |
| Context | give agents things they know | Knowledge, Memory (2) | 2 |
| System | look after Coffer and what every part shares | Secrets, Activity, Usage, Sync (4) | 4 |

The group is named **Run** rather than "Work": it is where an agent is set running — a chat, a
bot's conversations, later a workflow and its runs — and "work" reads as the user's own job,
which every group serves.

Pros: it passes the criterion — no group is over four at 1.0 or at sixteen — and the
growth that is "more of the same" (custom tools, more agents, ADE targets, more channels) adds
rows inside MCP servers, Agents and Channels and no entry at all. Every heading is a word a user
would say ("give Claude a new capability", "what context does it have"), not a framework term.
Each planned entry already has an obvious home, which is the test of a grouping that will not
be re-argued. Cons: five headings over thirteen entries means four groups of two at 1.0, so the
sidebar carries more headings than it strictly needs until the planned entries land; the line
between Capabilities and Context ("can do" against "knows") has to be learnt once, and a future
kind that is both — a skill that is mostly reference text — is filed by its kind, not its
content. A user of today's sidebar has to relearn where Model providers and Channels live.
**Wins**: it is the only grouping that meets the criterion at sixteen while keeping every
heading a single intent; the cost is a few lines of heading today, paid back as the groups fill.

### Option D — one flat list, ordered by how often each entry is used

No headings: the thirteen entries in one list, most-used first (Chat, Agents, Skills, MCP
servers, …), Sync last.

| Group | 1.0 | At ~16 |
| --- | --- | --- |
| (none) | 13 | 16 |

Pros: fewest pixels, no taxonomy to learn, the daily entries at the top. Cons: sixteen
undifferentiated rows is well past what a person scans at a glance — the reason the role ADR's
own flat option lost at eleven. "Most used" differs per person (a channel operator lives on
Channels; most people open it once) and shifts as features ship, so the order would either be
re-argued with every entry or silently wrong for most users. A flat list also hides the
distinctions the UI depends on: an agent is a consumer, a secret is shared infrastructure.
Frequency is better served by the command palette and by Overview, both of which the same
change adds. **Loses**: the criterion is failed by construction — one group of sixteen.

### Option E — fewer entries, each a page with tabs

Collapse the sidebar to six entries — Overview, Agents, Run, Capabilities, Context, System —
each a page whose tabs are today's entries (Capabilities › MCP servers | Skills; System ›
Secrets | Activity | Usage | Sync).

| Group | 1.0 | At ~16 |
| --- | --- | --- |
| (entries) | 6 | 6, with up to 4 tabs each |

Pros: the shortest possible sidebar; growth adds tabs, never entries. Cons: it puts tabs inside
tabs — Activity already has three, Settings five, Model providers two, and every detail page its
own — so the user reads two tab strips to find one table, and an address becomes
`/system?tab=activity&view=calls`. A tab strip hides its siblings behind a click where a
sidebar shows them; attention dots would need a second rendering on tabs; and Chat is a
full-height workspace with its own conversation list that cannot sit as a tab beside Channels
without giving up the screen it needs. It also merges pages with nothing in common but a heading
(Secrets and Usage) under one page header. **Loses**: it meets the size criterion only by
moving the groups one level down, where they cost more to use.

### Placement questions, answered under C'

**Chat and Channels are two entries.** Chat is the daily page: a person opens it many times a
day to hold a conversation. Channels is setup: pairing a bot, choosing its default agent,
checking its transport — done once per bot and revisited rarely. Merging them would put an
occasional configuration page in the path of the daily one, or bury bot setup behind a Chat
tab. A merged page would gain nothing either, because the conversations a channel carries are
already listed on the Chat page beside the web's own, with a badge naming the channel (spec
chat "Show every conversation on the Chat page"). They share a group because both are how work
with an agent happens; they are two entries because the user comes to each for a different
reason.

**Model providers belongs with Agents.** A provider is the endpoint and key an agent's model is
served from, and a connection and model are chosen per agent, on that agent's page (spec
provider-switching "Offer every connection operation on REST, CLI and web";
[LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md)).
The provider page is each agent's model configuration seen from the connection side — the page a
user visits while setting an agent up, not a capability the agent gains and not a machine
setting. Coffer's own model is a tab of the same page because it too is a choice among those
connections ([The Engine Owns Its Model](internal-engine-settings.md)). Filed under Capabilities
it would read as a tool the agent calls; filed under System it would read as a Coffer
preference, the placement the role ADR already rejected.

**Secrets is its own entry, in System.** A stored secret is shared infrastructure data: one key
can be cited by an MCP server, a model provider, a channel and a skill at once
([Resources Cite Secrets by Opaque Reference](credential-references.md)), so filing it under any
one of those pages leaves the other three blind to it. The page's job is cross-cutting — list
every secret, show what uses it, find the unused ones, refuse to delete one still cited (spec
credentials "Refuse to delete a credential still in use"), and move plaintext secret files into
the store — which is what System is for. It is an entry rather than a Settings tab because it
holds data the user manages, not a preference; Settings › Security keeps only what is about this
machine (where the master key lives), so a user never looks for a token among display
preferences. A secret field in a resource's own dialog stays where it is: a secret is still
entered where the thing that needs it is configured.

**Settings is a modal, not an entry.** Settings is opened rarely — to check
the daemon, move the master key, set retention, see the version — and what it holds is about this machine, not
about the vault's agents, capabilities or context. A sidebar row is the most visible place the
product has; spending one on a page opened a few times a year puts it beside pages used every
day, and with Usage in 1.0 it would fill System to five, the ceiling, before anything else
arrives. Desktop applications have a settled convention for this: preferences open from a fixed
control and ⌘, into a window of their own (macOS apps' Settings, VS Code, Linear), and a user
reaching for ⌘, looks nowhere else. So Settings opens from a gear in the sidebar footer, beside
the daemon status, and from ⌘,, as a large modal over the current page (spec web-ui "Open
Settings as a modal from the sidebar footer"). The cost is routing: the modal must stay
addressable, so each tab keeps `/settings/<tab>`, a deep link or the command palette opens it
over the page the user is on, a fresh load opens it over Overview, and closing returns to the
page underneath — the router has to carry a background location, where a page needed one route
per tab. A modal with no route would have been cheaper and would break every deep link, from
the footer's link to Settings › Daemon to the palette's Settings tabs.

## Decision

The sidebar is grouped by what the person comes to do, with Overview above the groups under no
heading:

```
  Overview                 总览
 AGENTS                   智能体
  Agents                   智能体
  Model providers          模型提供商
 RUN                      运行
  Chat                     聊天
  Channels                 消息渠道
 CAPABILITIES             能力
  MCP servers              MCP 服务器
  Skills                   技能
 CONTEXT                  上下文
  Knowledge                知识
  Memory                   记忆
 SYSTEM                   系统
  Secrets                  密钥
  Activity                 活动
  Usage                    用量
  Sync                     同步
 ──────────────────────────
  daemon status · ⚙ Settings (modal, ⌘,)   设置
```

Overview is ungrouped because it summarises every group; filing it under one would misname it,
and a heading over one entry groups nothing. In Chinese, "agent" is **智能体** everywhere in the
UI — group heading, entry, page titles and prose — under the one-name rule of spec web-ui "Call a
surface by one name everywhere".

Rules a future change must respect:

- A new entry joins the group that names what the user comes to it for. Workflows (with its
  Workflows and Runs tabs, scheduled tasks included) goes to Run; Rules and Sources go to
  Capabilities.
- Settings stays out of the sidebar: machine-level configuration joins a Settings tab, not an
  entry.
- Growth that is more of an existing thing — another agent, another channel, a custom tool, an
  ADE as a delivery target — is a row inside the existing page, never an entry.
- No group grows past five entries. A sixth is a reason to revisit this ADR, not to append.
- A new group needs a new intent, not a new kind.
- The sidebar still lists only shipped surfaces, and a switched-off experimental feature's entry
  is left out; a group whose every entry is left out leaves its heading out too.

## Consequences

- The entry set and groups are pinned by spec web-ui "Keep the sidebar to its thirteen entries"
  and "Group the sidebar by what the user comes to do"; changing either is a spec change.
- The old rule of one Resources entry per listed resource kind becomes one sidebar entry per
  listed resource kind, filed by intent (spec web-ui "Give each listed resource kind one sidebar
  entry"). The backend's resource framework is unchanged: "resource" stays the storage word and
  stops being a navigation word.
- Secrets becomes a page of its own (spec web-ui "Manage stored secrets on the Secrets page"),
  and Settings › Security narrows to machine-level items; the credential store's behaviour behind
  the page is specified by its own change.
- A user of the eleven-entry sidebar finds Model providers under Agents, Channels under Run and
  Settings behind the footer gear. Routes do not move, so no bookmark breaks.
- The router carries a background location so the Settings modal can be opened over any page
  and closed back to it; that is the price of keeping every Settings tab linkable.
- Four headings hold two entries each until the planned entries land; that is the accepted price
  of groups that do not have to be reshuffled when they do.
- The zh locale's label for agent changes from "Agent" to 智能体 across the UI, and the en/zh
  glossary in the frontend conventions records every group and entry label.
