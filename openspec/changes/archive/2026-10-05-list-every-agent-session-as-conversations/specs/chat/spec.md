## REMOVED Requirements

### Requirement: List conversations by latest activity
**Reason**: The Conversations page lists every agent's sessions, read through [agent-registry](../agent-registry/spec.md) "List every agent's sessions in one list", which lists a channel's conversations from the index when its source names channels only. The channel-only listing `GET /api/v1/chat/conversations` has no caller left.
**Migration**: Read `GET /api/v1/agent-sessions?source=<channel uid>[,…]`. The single-conversation read, rename, delete and interrupt routes under `/api/v1/chat/conversations/{id}` stay. A conversation's activity time is still bumped when a turn starts and when it ends.

## RENAMED Requirements

- FROM: `### Requirement: Show channel conversations on the Conversations page`
- TO: `### Requirement: Show every agent's sessions on the Conversations page`

## MODIFIED Requirements

### Requirement: Show every agent's sessions on the Conversations page
The web UI MUST carry a **Conversations** page (`/conversations`) that lists every session of
every managed agent, wherever it was started — in a terminal, by an IM channel (SeaTalk,
Telegram) or by New conversation — read through [agent-registry](../agent-registry/spec.md)
"List every agent's sessions in one list". It is a list with no conversation view and no reply
box; its header's one primary action is **New conversation** ("Start a new conversation in the
terminal"). The list has a header row naming its columns — **Title**, **Source**, **Agent**,
**Directory**, **Last active** — above rows grouped by day (**Today**, **Yesterday**, **Earlier**;
the group titles carry no counts), newest activity first; a column the list does not show has no
heading. A row MUST show the title, a
status word (**Running** with a success-coloured dot while a turn runs; **Needs you** with a
warning dot while the agent waits for an answer, when the session is a channel conversation's),
its **source** (for a channel conversation the platform's logo and name with where in the chat it
lives — `SeaTalk · DM`, a group by its name when Coffer knows it, a thread or topic rather than the
chat's main timeline, a parallel thread as `DM · Thread 2`; for any other session nothing), the
agent's badge and name, its working directory, and its last activity (the clock time for today and
yesterday, a date such as `Sep 22` for earlier). A running row carries an inline **Stop**, which
calls `POST .../interrupt` for that conversation with the semantics of "Pause the pending queue on
interrupt". Every row carries the split button of "Open a conversation in the terminal" and a
trailing **⋯** menu (Rename, Delete…), both always shown. Rename edits the title in place in the
row — Enter saves, Esc cancels — and Rename and Delete… act through the agent ("Rename and delete a
conversation through its agent"; [agent-registry](../agent-registry/spec.md) "Rename and delete a
native session through the agent"); Delete… asks first. The row shows no message text, because
Coffer stores none.

The filter row reads, in order, a search box over titles and working directories (`/` focuses it), a
**Source** pill (**This Mac**, then each channel shown as its platform's logo and `SeaTalk · Team
bot`, several at once), an **Agent** pill, and **Clear filters** once anything narrows the list; it
shows no result count. The filters and the search are applied by the server, so a filtered list
pages through matches only. All of it is in the URL — `?q=`, `?source=local|<channel uid>[,…]`,
`?agent=` — so a filtered list is a link, and a channel's **Conversations from this channel** link
opens `?source=<uid>`. The list reads 30 sessions and then 50 more as it is scrolled, and refreshes
when the window regains focus and on the change feed's chat events. When an agent's sessions could
not be read, one line above the list names it with **Retry** and the other agents' sessions are
listed. With no session at all the page is its header and one message; with filters that match
nothing it says so and offers **Clear filters**; a list that fails to load for every agent shows the
error in its own area with **Retry**. The page opens on the list rather than on a welcome or
suggestions page, which it does not have.

#### Scenario: a channel's conversations are listed with the channel's badge
- **GIVEN** a session started in a terminal and conversations opened by two IM channels
- **WHEN** the Conversations page's list renders
- **THEN** every one is listed, each channel conversation with a badge naming its channel and the terminal session with none
- **AND** filtering by one channel lists only that channel's

#### Scenario: a row names the chat and thread it came from
- **GIVEN** a conversation a SeaTalk direct chat opened, one a group thread opened, and one a `/thread` parallel conversation opened, whose turn is running
- **WHEN** the Conversations page's list renders
- **THEN** the first row's badge names SeaTalk and the direct chat, the second the group and its thread, and the third its `Thread N` mark
- **AND** each row shows its agent and working directory, and the third is marked running

#### Scenario: rows are grouped by day without counts
- **GIVEN** sessions last active today, yesterday and weeks ago
- **WHEN** the Conversations page's list renders
- **THEN** a header row names the columns Title, Source, Agent, Directory and Last active, and below it the groups Today, Yesterday and Earlier, none of them with a count
- **AND** a row from today shows its clock time and an earlier row its date

#### Scenario: the Channel pill filters by several channels
- **GIVEN** sessions started in a terminal and conversations from three channels
- **WHEN** the user ticks two channels in the Source pill, and then This Mac alone
- **THEN** first only those channels' conversations are listed with `?source=` naming both and Clear filters offered, then only the terminal sessions with `?source=local`

#### Scenario: a row's menu acts on one conversation
- **GIVEN** a session in the list
- **WHEN** the user opens its ⋯ menu
- **THEN** it offers Rename and Delete… and nothing else, and Rename edits the title in place in the row
- **AND** Delete… asks first, naming the session

#### Scenario: a list that fails to load says so
- **GIVEN** the listing fails for every agent
- **WHEN** the page renders
- **THEN** the list area shows an error with Retry, and Retry reads the list again

#### Scenario: one agent's sessions that cannot be read are named above the list
- **GIVEN** Claude Code's sessions listed and Codex named as unavailable
- **WHEN** the page renders
- **THEN** Claude Code's sessions are listed under one line saying Codex's sessions could not be read, with Retry

#### Scenario: a search that matches nothing is not an empty list
- **GIVEN** a list holding one session
- **WHEN** the owner searches for text no title or directory contains
- **THEN** nothing is listed and the list says nothing matches
- **AND** it does not show the empty-list message, and the search box keeps the query

#### Scenario: an empty conversation list offers no search
- **GIVEN** no agent has any session
- **WHEN** the conversation list renders
- **THEN** it shows the empty-list message, New conversation and no search box

#### Scenario: the page opens on the list with no welcome page
- **GIVEN** sessions of two agents
- **WHEN** the user opens `/conversations`
- **THEN** it opens the list with no welcome or suggestions page and no reply box, and New conversation is the header's one primary action

#### Scenario: the page stops a turn another surface started
- **GIVEN** a running turn started from a channel, with a message queued behind it
- **WHEN** the user presses Stop on its row, which calls `POST .../interrupt` for that conversation
- **THEN** the turn stops, its streamed text having reached the chat
- **AND** the queued message is held rather than auto-run

#### Scenario: running and waiting rows are marked from the daemon's turn state
- **GIVEN** a conversation whose turn is in flight and another that waits on a question
- **WHEN** the list renders
- **THEN** the first row reads Running with an inline Stop and the second reads Needs you
- **AND** both flags come from the daemon's in-memory turn state

### Requirement: Open a conversation in the terminal
A row of the Conversations page MUST hand its session to the agent's own
interface: pressing the row, or the main part of its split button **Open in
<terminal>** (named for the preferred terminal, e.g. **Open in iTerm**), MUST ask the
daemon to resume the session in the person's preferred terminal ([web-ui](../web-ui/spec.md)
"Let the user choose a terminal"; [daemon](../daemon/spec.md) "Open an agent session in a
terminal") — `claude --resume <session id>` for Claude Code and `codex resume <session id>` for
Codex, in the session's working directory. The split button's **▾** menu holds
**Open in <terminal>** for every other terminal on this machine — the system
terminal and each detected one — which opens the session there once and leaves the
preference as it is, then **Copy command**, which copies the same command line for
the person to run anywhere: the same shape as the hand-off button. A channel conversation
that has no native session yet — no turn has run on it — cannot be opened: its split button
is disabled and says why, and it offers no Copy command. An open the daemon refuses shows its
reason in a toast beside Copy command as the way out. Agent › Sessions rows use the same row and
the same behaviour ([agent-registry](../agent-registry/spec.md) "Open an agent's sessions from its Sessions tab").

#### Scenario: a row opens its session in the preferred terminal
- **GIVEN** a Claude Code session `abc-123` in `/work/api` and a preferred terminal
- **WHEN** the user presses its row
- **THEN** the daemon is asked to open `claude --resume abc-123` in `/work/api` in that terminal, for the session's agent
- **AND** a Codex session is opened as `codex resume <id>` the same way

#### Scenario: the ▾ menu opens the session in another terminal once
- **GIVEN** a session and iTerm as the preferred terminal
- **WHEN** its row renders and the user opens the ▾ menu and chooses Open in System terminal
- **THEN** the main part reads Open in iTerm, the menu does not repeat iTerm, and the daemon is asked to open the session in the system terminal
- **AND** the preferred terminal is still iTerm

#### Scenario: copy command copies the resume command
- **GIVEN** a session
- **WHEN** the user opens the ▾ menu and chooses Copy command
- **THEN** the command line for resuming that session in its directory is copied

#### Scenario: a conversation with no native session cannot be opened
- **GIVEN** a channel conversation on which no turn has run
- **WHEN** its row renders
- **THEN** the split button is disabled with a tooltip saying there is no session yet, and Copy command is not offered

#### Scenario: a refused open is reported with a way out
- **GIVEN** a daemon that refuses the terminal open
- **WHEN** the user presses a row
- **THEN** a toast shows the reason and offers Copy command

## ADDED Requirements

### Requirement: Start a new conversation in the terminal
The Conversations page header, and an agent's Sessions tab beside its search box, MUST carry
**New conversation**. It opens a dialog of two fields — **Agent**, the managed agents, preset to
the one chosen last (on a Sessions tab, that tab's agent), and **Working directory**, preset to
Coffer's workspace `~/.coffer/content/workspace` with a folder picker. The dialog's confirm is a
split button named for the preferred terminal, **Open in <terminal>**, whose ▾ offers every
other terminal on this machine for this once. Confirming MUST ask the daemon to start a blank
session of that agent in that directory in that terminal ([daemon](../daemon/spec.md) "Open an
agent session in a terminal") and close the dialog once the daemon has started it; a refusal shows
its reason in the dialog, which stays open. The new session is listed once the agent has recorded
it, on the list's next refresh. With no managed agent the button is disabled and says why.

#### Scenario: New conversation starts the chosen agent in the chosen directory
- **GIVEN** Claude Code and Codex managed, Codex chosen last, and iTerm the preferred terminal
- **WHEN** the user presses New conversation, picks `/work/api` and confirms Open in iTerm
- **THEN** the dialog opened with Codex and the workspace directory, and the daemon is asked to start a blank Codex session in `/work/api` in iTerm
- **AND** the dialog closes

#### Scenario: a refused start keeps the dialog open
- **GIVEN** a daemon that refuses the terminal open
- **WHEN** the user confirms New conversation
- **THEN** the dialog stays open and shows the reason
