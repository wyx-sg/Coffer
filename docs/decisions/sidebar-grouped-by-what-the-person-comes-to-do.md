# The Sidebar Is Grouped by What the Person Comes to Do: Agents, Run, Capabilities, Context, System

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [Resource Framework Upfront](resource-framework-upfront.md),
[Experimental Features Instead of a Release Branch](experimental-features-instead-of-a-release-branch.md),
[LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md),
[The Engine Owns Its Model; Its Endpoint Is Borrowed From a Flagged Connection](internal-engine-settings.md),
[Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md),
[Channels Are Thin Transport Adapters Over One Shared Core, Supervised In-Daemon](channel-adapter-framework.md),
[Resources Cite Secrets by Opaque Reference, Resolved Only at the Moment of Use](credential-references.md),
[Standalone Secrets Are Named `coffer://secret/` References, Injected Only Into One Child Process](standalone-secrets-are-named-references-injected-into-one-child.md),
spec web-ui "Group the sidebar by what the user comes to do",
spec web-ui "Keep the sidebar to its fifteen entries",
spec web-ui "Manage custom tools on their own page",
spec web-ui "Show every CLI a skill requires on the CLIs page",
spec web-ui "Give each listed resource kind one sidebar entry",
spec web-ui "List only shipped surfaces in the sidebar",
spec web-ui "Call a surface by one name everywhere",
spec web-ui "Manage stored secrets on the Secrets page",
spec web-ui "Open Settings as a modal from the sidebar footer",
spec chat "Show every conversation on the Conversations page",
spec provider-switching "Offer every connection operation on REST, CLI and web",
spec secret "Refuse to delete a secret still in use",
spec web-ui "Show what needs the user and each area's health on Overview",
spec chat "Mirror a web reply into the channel it came from",
the change `openspec/changes/archive/2026-10-01-revise-web-ui-ia/`

## Context

The backend models every managed asset as a resource of some kind on one kind-agnostic
framework ([Resource Framework Upfront](resource-framework-upfront.md)); the web UI has to decide
how those kinds, plus things that are not resources at all (the activity record, sync, secrets,
settings), appear in navigation. The navigation should not be re-argued every time something
ships, it should read as what the product does today, and the grouping has to survive the one
entity that does not behave like the others: an agent *uses* the vault rather than living in it.

The sidebar this decision replaced held eleven entries in three role groups — Agents (Agents,
Chat), Resources (MCP servers, Skills, Knowledge, Memory, Model providers, Channels), System
(Activity, Sync, Settings) — chosen so that "a new asset kind is one more Resources row and never
a new group".

The rebuild of the UI makes that promise expensive. Five entries arrive with it: **Overview**, the landing
page; **Secrets**, a page that lists every stored secret with what uses it, which the
secret store has never had
([Standalone Secrets Are Named `coffer://secret/` References](standalone-secrets-are-named-references-injected-into-one-child.md)
makes every stored secret listable with its reference count); and **Usage**, token use metered
at the model proxy and the official remaining quota of subscription agents, which is in 1.0;
**Custom tools**, HTTP APIs Coffer serves to agents as tools, imported from an OpenAPI document
or defined by hand; and **CLIs**, the command-line tools skills require. One entry leaves: **Settings**
becomes a modal opened from the sidebar footer (argued below). That is fifteen. The roadmap
after 1.0 already names three more entries, and several additions that must *not* become
entries:

| Future addition | Lands as |
| --- | --- |
| Workflows, with a Workflows tab and a Runs tab; scheduled tasks are workflows with a schedule trigger | one entry |
| Rules (instructions projected into each agent's instruction files) | one entry |
| Sources (read-only git sources a vault subscribes to, for skills and the like) | one entry |
| More agents; agentic development environments (ADEs) as delivery targets | rows on Agents |
| More channels (IM transports) | rows on Channels |

So the navigation has to hold about **eighteen entries** without being regrouped, and every
kind of growth that is "more of the same" has to land inside a page. The criterion every option
below is measured against: **at ~18 entries, no group grows past ~5**. Five is where a group
heading still reads as one idea at a glance; past it, a group becomes a list the eye scans row by
row, which is what grouping was meant to avoid.

Rules is not in 1.0: projecting rules into each agent's instruction files is deferred, and no
entry ships before its feature (web-ui "List only shipped surfaces in the sidebar"). It is
counted here because the grouping must already have room for it.

Five placement questions have to be answered by whatever grouping wins, because each was
contested while the rebuild was designed:

- **Conversations and Channels.** Both put a person in a conversation with an agent; should they
  be one entry, and where does a channel's history live?
- **Model providers.** Is a provider an asset like an MCP server, a setting, or part of setting
  up an agent?
- **Secrets.** A secret is cited by MCP servers, model providers, channels and skills; where does
  a page for all of them go, and what stays on Settings › Security?
- **Settings.** Is Settings a sidebar entry at all?
- **Custom tools and CLIs.** A custom tool is an MCP server underneath, and a CLI is something a
  skill needs; do they need entries of their own?

## Options Considered

Entry counts below are *1.0* (15, with Overview, Secrets, Usage, Custom tools and CLIs, and
Settings as a modal) → *at ~18* (with Workflows, Rules and Sources). Overview is ungrouped in every option, for the
reason given under the Decision, and Settings is a modal in every option, for the reason given
under the placement questions.

### Option A — role groups, as the eleven-entry sidebar had them: Agents, Resources, System

Keep the three role groups of the eleven-entry sidebar — **Agents** (the consumers), **Resources**
(the assets agents draw on, exactly one entry per resource kind with a list surface; a channel sits
here as a credentialed transport the vault owns, a model provider as a vendor endpoint and its key)
and **System** (cross-cutting tooling) — and add the new entries where its rule puts them: Secrets, Custom tools and CLIs as Resources rows, Usage under System,
Workflows under Agents (a thing done with agents), Rules and Sources under Resources.

| Group | 1.0 | At ~18 |
| --- | --- | --- |
| Agents | Agents, Chat (2) | + Workflows (3) |
| Resources | MCP servers, Custom tools, Skills, CLIs, Knowledge, Memory, Model providers, Channels, Secrets (9) | + Rules, Sources (11) |
| System | Activity, Usage, Sync (3) | 3 |

Pros: no migration of the user's mental map; the rule that places an entry is one question
("consumer, asset or tooling?") and has never been hard to answer; a new asset kind is one more
Resources row and never a new group; the consumer/asset distinction stays visible. Cons: it fails the criterion
already at 1.0 — nine Resources rows — and reaches eleven, more than half the sidebar under one
heading. "Resource" is the framework's word, not the user's: nobody comes to Coffer to "manage
resources"; they come to give an agent a tool, to tell it something, or to wire up a bot. The
role axis also puts Channels, a bot the user sets up occasionally, between Model providers and
Secrets rather than beside Chat, the page where its conversations show up. **Loses** on the
criterion; the one-big-group shape is exactly what the other options try to fix.

### Option B — intent groups for the verbs, one Resources group for the nouns

Group what the user *does* by intent — a Run group (Conversations, Channels, later Workflows) and System
— and keep one Resources group for everything that is configured: Agents, Model providers, MCP
servers, Custom tools, Skills, CLIs, Knowledge, Memory, Secrets.

| Group | 1.0 | At ~18 |
| --- | --- | --- |
| Run | Conversations, Channels (2) | + Workflows (3) |
| Resources | Agents, Model providers, MCP servers, Custom tools, Skills, CLIs, Knowledge, Memory, Secrets (9) | + Rules, Sources (11) |
| System | Activity, Usage, Sync (3) | 3 |

Pros: Conversations and Channels sit together, where a user looks for "talking to an agent"; three
headings stay easy to learn. Cons: it moves the problem rather than solving it — Resources is
nine, then eleven — and it puts Agents, the subject of the whole product, in the middle of
a list of the things agents use, the mislabelling a single-axis grouping (everything is a resource kind) was rejected for.
**Loses** on the criterion for the same reason as A.

### Option C — five intent groups: Agents, Run, Capabilities, Context, System (chosen)

Split the configured nouns by what the user comes to do with them, so every group is one
intent:

| Group | What the user comes to do | 1.0 | At ~18 |
| --- | --- | --- | --- |
| Agents | set up the agents and the models they run on | Agents, Model providers (2) | 2 |
| Run | put an agent to work, directly or through an IM bot | Conversations, Channels (2) | + Workflows (3) |
| Capabilities | give agents things they can do | MCP servers, Custom tools, Skills, CLIs (4) | + Rules, Sources (6) |
| Context | give agents things they know | Knowledge, Memory (2) | 2 |
| System | look after Coffer and what every part shares | Secrets, Activity, Usage, Sync (4) | 4 |

The group is named **Run** rather than "Work": it is where an agent is set running — a
conversation, from Coffer or from an IM bot, later a workflow and its runs — and "work" reads as the user's own job,
which every group serves.

Pros: it passes the criterion at 1.0 — no group is over four — and the growth that is "more of
the same" (more agents, ADE targets, more channels, another custom tool) adds rows inside
Agents, Channels and Custom tools and no entry at all. At eighteen it is the only option that
misses by one group rather than by construction: Capabilities reaches six when both Rules and
Sources land, which under the rules below makes that change revisit Capabilities instead of
appending. Every heading is a word a user
would say ("give Claude a new capability", "what context does it have"), not a framework term.
Each planned entry already has an obvious home, which is the test of a grouping that will not
be re-argued. Cons: five headings over fifteen entries means three groups of two at 1.0, so the
sidebar carries more headings than it strictly needs until the planned entries land;
Capabilities is the fullest group and is the one to split or trim when Rules and Sources arrive; the line
between Capabilities and Context ("can do" against "knows") has to be learnt once, and a future
kind that is both — a skill that is mostly reference text — is filed by its kind, not its
content.
**Wins**: it is the only grouping that meets the criterion at 1.0 and stays within one entry of it at eighteen while keeping every
heading a single intent; the cost is a few lines of heading until the groups fill.

### Option D — one flat list, ordered by how often each entry is used

No headings: the fifteen entries in one list, most-used first (Conversations, Agents, Skills, MCP
servers, …), Sync last.

| Group | 1.0 | At ~18 |
| --- | --- | --- |
| (none) | 15 | 18 |

Pros: fewest pixels, no taxonomy to learn, the daily entries at the top. Cons: eighteen
undifferentiated rows is well past what a person scans at a glance — the reason a flat list already
stops being scannable at eleven. "Most used" differs per person (a channel operator lives on
Channels; most people open it once) and shifts as features ship, so the order would either be
re-argued with every entry or silently wrong for most users. A flat list also hides the
distinctions the UI depends on: an agent is a consumer, a secret is shared infrastructure.
Frequency is better served by the command palette and by Overview, both of which the same
change adds. **Loses**: the criterion is failed by construction — one group of eighteen.

### Option E — fewer entries, each a page with tabs

Collapse the sidebar to six entries — Overview, Agents, Run, Capabilities, Context, System —
each a page whose tabs are the entries (Capabilities › MCP servers | Custom tools | Skills |
CLIs; System › Secrets | Activity | Usage | Sync).

| Group | 1.0 | At ~18 |
| --- | --- | --- |
| (entries) | 6 | 6, with up to 6 tabs each |

Pros: the shortest possible sidebar; growth adds tabs, never entries. Cons: it puts tabs inside
tabs — Activity already has three, Settings five, Model providers two, and every detail page its
own — so the user reads two tab strips to find one table, and an address becomes
`/system?tab=activity&view=calls`. A tab strip hides its siblings behind a click where a
sidebar shows them; attention dots would need a second rendering on tabs; and Conversations is a
full-height workspace with its own conversation list that cannot sit as a tab beside Channels
without giving up the screen it needs. It also merges pages with nothing in common but a heading
(Secrets and Usage) under one page header. **Loses**: it meets the size criterion only by
moving the groups one level down, where they cost more to use.

### Placement questions, answered under C

**Conversations and Channels are two entries, and history lives in Conversations.** Conversations
is the daily page: every conversation Coffer runs — from SeaTalk, Telegram and Coffer's own UI,
which is modelled as a built-in "Coffer" source — in one list with a source badge and filters, each
opening on its full exchange with a reply box that continues it (spec chat "Show every
conversation on the Conversations page"). Channels is setup only: pairing a bot, choosing its
default agent, checking its connection — done once per bot and revisited rarely — with a link to
Conversations filtered to that channel. A survey made while the rebuild was designed (OpenClaw,
Hermes Agent, cc-connect, claude-code-telegram, kimaki, Claude Code Channels, Happy, Omnara,
Botpress and Chatwoot) found that no product puts conversation history
inside its channel or config page: history is one global list with a channel badge and filter,
the channel page holds only configuration and connection status (Hermes, Chatwoot), and every
product with a UI lets the user send from it, with its own web chat modelled as just another
channel (OpenClaw's WebChat, Botpress's Webchat, Chatwoot's live chat). A separate "Chat" page
beside a channel history (Hermes's split) was the weaker pattern, because it puts history in two
places; so the entry is named Conversations, not Chat, and Coffer's own UI is a source, not a
second kind of conversation. They share a group because both are how work with an agent happens;
they are two entries because the user comes to each for a different reason. A reply sent from
Coffer into a channel-opened conversation is also delivered back to that channel (spec chat
"Mirror a web reply into the channel it came from").

**Model providers belongs with Agents.** A provider is the endpoint and key an agent's model is
served from, and a connection and model are chosen per agent, on that agent's page (spec
provider-switching "Offer every connection operation on REST, CLI and web";
[LLM Connections Are Projected Into Each Agent's Own Config File](provider-connections-projected-into-agent-config.md)).
The provider page is each agent's model configuration seen from the connection side — the page a
user visits while setting an agent up, not a capability the agent gains and not a machine
setting. The page is one table of connections: which agent runs on a connection is read on the
connection's detail page and switched only on the agent's own Model tab. Coffer's own model is
not on it — it configures Coffer rather than an agent, so it is a section of Settings › General
that picks a provider and then its model ([The Engine Owns Its Model](internal-engine-settings.md)). Filed under Capabilities
it would read as a tool the agent calls; filed under System it would read as a Coffer
preference, which a provider is not.

**Secrets is its own entry, in System.** A stored secret is shared infrastructure data: one key
can be cited by an MCP server, a model provider, a channel and a skill at once
([Resources Cite Secrets by Opaque Reference](credential-references.md)), so filing it under any
one of those pages leaves the other three blind to it. The page's job is cross-cutting — list
every secret, show what uses it, find the unused ones, refuse to delete one still cited (spec
secret "Refuse to delete a secret still in use"), and move plaintext secret files into
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
reaching for ⌘, looks nowhere else. So Settings opens from a labelled Settings row at the bottom of the sidebar, above
the daemon status, and from ⌘,, as a large modal over the current page (spec web-ui "Open
Settings as a modal from the sidebar footer"). The cost is routing: the modal must stay
addressable, so each tab keeps `/settings/<tab>`, a deep link or the command palette opens it
over the page the user is on, a fresh load opens it over Overview, and closing returns to the
page underneath — the router has to carry a background location, where a page needed one route
per tab. A modal with no route would have been cheaper and would break every deep link, from
the footer's link to Settings › Daemon to the palette's Settings tabs.

**Custom tools and CLIs are entries of their own.** A group of custom tools is an MCP server of
the HTTP API transport, served by the same gateway machinery, so it could have been a filter on
MCP servers. It gets its own entry for discoverability: a user who wants to turn an API into
tools looks for "custom tools", not for a transport option inside a list of servers someone else
wrote, and its add flow (import an OpenAPI spec and pick operations, or define one request) is
unlike adding a server from a README. CLIs is an entry because it has
data of its own — whether each command a skill requires is installed, which version, whether it
is logged in — and actions shown nowhere else: a prompt that hands the install to an agent,
the login command, check again. Folded into Skills it would repeat per skill what is one fact
per command, and a command several skills need would show its problem in several places. Both
sit under Capabilities, because both are about what agents can do.

## Decision

The sidebar is grouped by what the person comes to do:

- **Overview**, above the groups, under no heading.
- **Agents** — set up the agents and the models they run on: Agents, Model providers.
- **Run** — put an agent to work, directly or through an IM bot: Conversations, Channels.
- **Capabilities** — give agents things they can do: MCP servers, Custom tools, Skills, CLIs.
- **Context** — give agents things they know: Knowledge, Memory.
- **System** — look after Coffer and what every part shares: Secrets, Activity, Usage, Sync.
- A labelled Settings row in the sidebar footer, above the daemon status, opens Settings as a
  modal (also on ⌘,); it is in no group.

Fifteen entries with every experimental feature on; spec web-ui "Keep the sidebar to its fifteen
entries" owns the list and the routes, and `NAV_GROUPS` in `frontend/src/lib/navigation.ts` is the
one list the sidebar, the command palette and the Settings modal read. An entry whose experimental
feature is switched off is left out; the four experimental features own Model providers, Usage,
Knowledge, Memory and Sync, and Conversations and Channels are always there.

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
- Growth that is more of an existing thing — another agent, another channel, another custom
  tool, an ADE as a delivery target — is a row inside the existing page, never an entry.
- No group grows past five entries. A sixth is a reason to revisit this ADR, not to append.
- A new group needs a new intent, not a new kind.
- The sidebar still lists only shipped surfaces, and a switched-off experimental feature's entry
  is left out; a group whose every entry is left out leaves its heading out too.

## Consequences

- The entry set and groups are pinned by spec web-ui "Keep the sidebar to its fifteen entries"
  and "Group the sidebar by what the user comes to do"; changing either is a spec change. The
  groups and entries are implemented in `frontend/src/lib/navigation.ts` (`NAV_GROUPS`) and
  rendered by `frontend/src/components/SidebarNav.tsx`; the Settings modal is
  `frontend/src/pages/settings/SettingsModal.tsx`.
- One sidebar entry per listed resource kind, filed by intent (spec web-ui "Give each listed
  resource kind one sidebar entry"). The backend's resource framework is unaffected: "resource"
  stays the storage word and is not a navigation word.
- Secrets is a page of its own (spec web-ui "Manage stored secrets on the Secrets page"), and
  Settings › Security carries only machine-level items.
- The router carries a background location so the Settings modal can be opened over any page
  and closed back to it; that is the price of keeping every Settings tab linkable.
- With experimental features switched off, whole groups can leave the sidebar (a group with every
  entry left out leaves its heading too).
- Three headings hold two entries each until the planned entries land; that is the accepted price
  of groups that do not have to be reshuffled when they do.
- Capabilities holds four entries and would hold six with Rules and Sources, so the change
  that adds the second of them has to revisit Capabilities rather than append to it.
- Not built yet: the Workflows, Rules and Sources entries. Each is placed (Run, Capabilities,
  Capabilities) but ships with its feature.
- Custom tools and CLIs each have a page of their own (spec web-ui "Manage custom tools on their
  own page", "Show every CLI a skill requires on the CLIs page"); the MCP servers Add dialog adds
  servers only.
- In Chinese, "agent" is 智能体 everywhere in the UI, and the en/zh glossary in the frontend
  conventions records every group and entry label.
