## MODIFIED Requirements

### Requirement: Show what needs the user and each area's health on Overview
Overview MUST answer "is everything OK, and what needs me?" at a glance, from
the capabilities' own reads and never a route of its own. **Needs you** comes
first: one row per item of the attention list ([resource-framework](../resource-framework/spec.md)
"Report what needs a person across every kind"), most severe first and then
oldest, each with its resource and kind, the reason in a sentence, since when
where that is known, and exactly one action that opens the page — or the tab —
where the item is dealt with. The action reads what it does for that kind and
reason, not the bare verb — a channel's check is **Reconnect channel**, sync's
review **Review held changes**, a memory hook's repair **Repair hook** — behind a
small icon for its verb (a key for a secret, an eye for a review, a plug for connecting,
a wrench for repairing, a refresh for checking or testing again), and the reason
may wrap to two lines before it is cut, its whole text on hover. An action that is a non-GET call into Coffer's
own state needing no preview — testing an MCP server again, probing a command
again — MUST run in place instead: the button turns into a disabled
"Retrying…" or "Checking…", the reason gains an accent line ("Starting
postgres… it leaves this list once it answers."), and that lasts until the
attention list has been read again after the call; a row still listed then
returns to its button, and a failed call returns it at once with the error as
a toast. Every other action — connecting an agent or repairing its config
(writes into the agent's own files, previewed on their page), adding a secret,
turning approval on, and every read-only review — keeps opening its page. Every row MUST also
carry the hand-off split button, Ask an agent ▾ with Copy prompt behind it, and a ⋯ menu
holding Ignore — the daemon's prompt as given (every item carries one, the
kind's own where it has one); the list scrolls inside a frame of about six
rows, under its title, which shows how many items it holds. An attention source that failed MUST be named
above the rows in one muted status line, saying that what it would report is missing. Rows MUST clear
themselves as problems resolve: the page follows the daemon's event stream and
rereads the list when an `attention` change arrives. **Health** follows: one
tile per sidebar area whose feature is switched on — Agents, MCP servers,
Skills, Knowledge, Memory, Model providers, Channels, Sync, Custom tools, CLIs,
Secrets and Usage, in that order (Conversations show in Recent activity) —
each with a status word drawn from that area's attention items (Secrets, which
has no attention source, words its own list: a secret missing on this machine is
a warning, one nothing uses is plain subtle text with no dot; Usage shows its
period, "Last 24 h", and no health), a count from its own list and a one-line
summary, opening the area's page — Usage, which is a tab of Model providers, opening that tab; an area with no backend has no tile. Agents
and Channels count "1 of 2" with the unit "connected" — for Agents only the
items about connecting count, so a hook edited by hand or one the agent has not approved does not make an agent
"not connected" — and Channels names the reconnecting one ("SeaTalk
reconnecting since 13:41"), otherwise the names joined with " · ". Knowledge's
line reads "4 collections · edited today 13:30", Memory's "Last update 14 min
ago", Sync's number is when its last round ended ("4 min ago", "last round")
over "1 behind · 0 ahead", and Usage counts the tokens of the last 24 hours in
one decimal ("2.1M"). A CLI tile words its problem by reason when every item
shares one ("1 not logged in", "1 outdated", "1 missing") and generically
("2 need attention") otherwise. Each tile loads and fails
on its own: a failed tile says what failed, shows the failed request in mono
("GET /api/v1/overview · knowledge · 503 · trace 01JA2M7X4Q"), and offers Retry
and a link to its page while the rest of the page keeps working. **Recent activity** lists the last few changes
with a link to Activity, leaving out changes to a resource whose experimental
feature is switched off. With nothing needing the user the list is a calm "all
good" card rather than an empty space, with one sentence on what is fine — the
agents connected, the servers answering and, while sync is on and has nothing
held, the vault in sync — each clause only for an area with something to report. With no agent registered the page is
the first-run panel alone: the supported agents with their config folders and
whether each was found on this machine, the found ones ticked, and **Review
and connect** opening the connection review for the ticked ones (every file
change shown before Coffer writes it); with none found it says so and its first
step is **Scan again**, each agent not found carrying an **Install** link to its
official install page; both offer adding an agent by hand, and the first step
for what agents share follows.

#### Scenario: overview lists what needs the user, most severe first
- **GIVEN** two failing MCP servers, one failing for five hours and one for two, a skill whose link drifted an hour ago, and an agent the user has not connected
- **WHEN** the user opens Overview
- **THEN** Needs you lists the older failing server first, then the other, then the skill, then the agent, each with its reason, since when where that is known, and one action opening the page or tab where it is dealt with

#### Scenario: health tiles carry the numbers and lines of Overview's board
- **GIVEN** two agents where one is not connected and the other's hook was edited by hand, a reconnecting channel, a knowledge collection edited a minute ago, a memory partition updated 14 minutes ago, a sync round that ended 4 minutes ago with one commit behind, a command that is not logged in, and a secret nothing uses
- **WHEN** the user opens Overview
- **THEN** Agents reads "1 of 2 connected" and "1 to connect", Channels "0 of 1" with "SeaTalk reconnecting since" a time, Knowledge "1 collection · edited" a time, Memory "Last update 14 min ago", Sync "4 min ago", "last round" and "1 behind · 0 ahead", CLIs "1 not logged in", Secrets "1 unused", and Usage "2.1M" with "Last 24 h"

#### Scenario: a row's action that runs in place shows it is in progress
- **GIVEN** a failing MCP server in Needs you whose action is to test it again, and an agent row whose action is to connect it
- **WHEN** the user clicks the server's action
- **THEN** the server's button reads "Retrying…" and is disabled, its reason carries "Starting <name>… it leaves this list once it answers.", and the test is called once
- **AND** once the list is read again with the server still listed, its button returns to normal, while the agent row's action stayed a link to its page throughout

#### Scenario: a needs-you row offers the item's hand-off in its menu
- **GIVEN** an attention item carrying a hand-off prompt, and a managed agent available
- **WHEN** the user opens the split button's menu and chooses Copy prompt, then presses Ask an agent
- **THEN** the daemon's prompt is copied as given, and Ask an agent opens New conversation and then the draft with the prompt in its composer, unsent
- **AND** with no managed agent available the row offers a Copy prompt button only, and every row's ⋯ menu ends with Ignore

#### Scenario: overview shows a calm card when nothing needs the user
- **GIVEN** an attention list with no items and no failed source, two connected agents, two enabled MCP servers and sync on with nothing held
- **WHEN** the user opens Overview
- **THEN** Needs you shows "Nothing needs you" with when it was checked and the sentence "Both agents are connected, 2 servers are answering and your vault is in sync. Anything that needs you shows up here.", and the health tiles show their areas as fine

#### Scenario: a needs-you row's action reads what it does for its kind
- **GIVEN** an attention item on a channel whose verb is check, and one on sync whose verb is review
- **WHEN** the user opens Overview
- **THEN** the channel's action reads Reconnect channel and carries an icon, and sync's reads Review held changes

#### Scenario: overview welcomes a first run with the agents to connect
- **GIVEN** a vault with no agent registered
- **WHEN** the user opens Overview
- **THEN** the page offers to connect the supported agents, naming which were found on this machine, followed by the first step for what they share
- **AND** with no supported agent found it says none was found and offers Scan again in place of connecting

#### Scenario: one area failing to load leaves the rest of overview working
- **GIVEN** the skills read fails while every other read answers
- **WHEN** the user opens Overview
- **THEN** the Skills tile says it could not load, with the failed request in mono, Retry and a link to Skills, and every other tile and the Needs you list render

#### Scenario: overview hides an area whose backend or feature is off
- **GIVEN** an area owned by a registered experimental feature that is switched off
- **WHEN** the user opens Overview
- **THEN** there is no tile for that area, while Custom tools, CLIs, Secrets and Usage each have one

#### Scenario: a resolved problem leaves overview on its own
- **GIVEN** Overview open with one item in Needs you
- **WHEN** the problem is resolved and the daemon announces an `attention` change
- **THEN** the page rereads the attention list and the row disappears without a reload

### Requirement: Hand a machine-dependent problem to an agent with one split button
Installing, setting up, logging in and troubleshooting depend on the machine, so a problem whose fix
is outside Coffer and for which the backend wrote a concrete prompt MUST be handed over with one split
button, **Ask an agent ▾**, never two buttons: pressing the button opens a draft conversation with
the prompt typed in and sends nothing until the person presses Send; the menu's one item, **Copy
prompt**, copies the daemon's prompt as given for an agent outside Coffer and answers with a
"Prompt copied" toast. With no Coffer-managed agent installed only **Copy prompt** is offered, with
the one-sentence help beside it. The split button sits after the state's own buttons (Check again,
Retry, View log), appears once per problem, never on a healthy, success or empty state, and never for
a missing secret or an approval, which only the person can give. Wherever another requirement names
Copy prompt and Ask an agent together, they are this button's menu item and button. On a Needs you
row the same split button sits beside the row's action, and the ⋯ menu holds Ignore.

#### Scenario: the split button hands a prompt over or copies it
- **GIVEN** a problem with a prompt and a managed agent installed
- **WHEN** the person presses Ask an agent, and separately opens its menu and chooses Copy prompt
- **THEN** a draft conversation opens with the prompt typed in and nothing sent, and the prompt is copied as given with a "Prompt copied" toast
- **AND** with no managed agent installed only Copy prompt is offered
