## ADDED Requirements

### Requirement: List every agent's sessions in one list
The system MUST expose `GET /api/v1/agent-sessions`, one listing of the native sessions of
every managed agent, each asked of the agent exactly as "List an agent's native sessions
through the agent" says and merged newest activity first, with agent key and `session_id`
as the tie-breaks. Each row carries what that listing's row carries plus the agent's key.
It MUST page by one opaque cursor over all the agents ([resource-framework](../resource-framework/spec.md)
"Page growing lists by an opaque cursor") and carry no `total`, because an agent may not
count its sessions. It MUST narrow, in the server, by `agent` (a comma-separated set of agent
keys: only those agents are asked), by `source` (a comma-separated set of `local` — a session
no channel conversation points at — and channel uids — a session that channel's conversation
points at) and by `q`, passed to each agent's own search; a cursor MUST be bound to the
filters it was issued for. When `source` names channels only, the rows are those channels'
conversations from the conversation index, so a conversation on which no turn has run is
listed, without a session. An agent whose listing fails MUST be left out of the page and
named under `unavailable` with its reason, while the other agents are listed. The read
carries no session text and is not audited.

#### Scenario: sessions from two agents are listed in one order
- **GIVEN** Claude Code with sessions last active at 10:00 and 08:00, and Codex with one last active at 09:00
- **WHEN** `GET /api/v1/agent-sessions` is read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the 10:00 Claude Code and 09:00 Codex sessions, each with its agent key, and the second the 08:00 one with a `null` `next_cursor`
- **AND** neither answer carries a `total`

#### Scenario: the listing narrows by source and agent
- **GIVEN** a Claude Code session started in a terminal and one a SeaTalk conversation points at, and a Codex session
- **WHEN** the listing is read with `source=local`, then with `source=<SeaTalk uid>`, then with `agent=codex`
- **THEN** the first lists the terminal session and the Codex one, the second only the SeaTalk one with its channel binding, and the third only Codex's
- **AND** a cursor issued for one set of filters is `CURSOR_INVALID` for another

#### Scenario: a channel conversation with no session yet is listed under its channel
- **GIVEN** a SeaTalk conversation on which no turn has run
- **WHEN** the listing is read with `source=<SeaTalk uid>`
- **THEN** it is listed with its title and channel binding and a null `session_id`

#### Scenario: one agent failing leaves the others listed
- **GIVEN** Claude Code with sessions and a Codex whose listing fails
- **WHEN** the listing is read
- **THEN** Claude Code's sessions are listed and `unavailable` names Codex with the reason

## MODIFIED Requirements

### Requirement: Open an agent's sessions from its Sessions tab
The agent detail page's **Sessions** tab MUST list the agent's native sessions
("List an agent's native sessions through the agent") as rows of the same kind the
Conversations page uses ([chat](../chat/spec.md) "Show every agent's sessions on the Conversations page"), without the
channel column unless the session is a channel conversation's: title, working directory and last
activity, with the channel, the Running / Needs you mark and an inline **Stop** when it is. A search
box over title and working directory filters the list in the server, and the list pages by
cursor as it is scrolled. Pressing a row, or the main part of its split button **Open in
<terminal> ▾**, MUST open the session in the preferred terminal exactly as
[chat](../chat/spec.md) "Open a conversation in the terminal" says, asking first when the session is
busy ("Ask before opening a session that is running"). An always-shown **⋯** menu holds **Rename** (in
place) and **Delete…**, which asks first and says the session is deleted from the agent and cannot be recovered. A
failure to load the list shows in the list's area with a Retry. The tab shows no session text.
Beside the search box the tab carries **New conversation**, which opens the dialog of
[chat](../chat/spec.md) "Start a new conversation in the terminal" with this agent chosen.
The tab is the Conversations page's list narrowed to this agent: the same header row, rows,
actions and paging, without the Agent column.

#### Scenario: a session row opens in the terminal
- **GIVEN** an agent's Sessions tab listing a session `abc-123` in `/work/api`
- **WHEN** the user presses the row
- **THEN** the daemon is asked to open the agent's resume command for that session in `/work/api` in the preferred terminal

#### Scenario: a session that is a channel conversation shows its channel
- **GIVEN** a listed session that a SeaTalk conversation points at, with a turn running
- **WHEN** the tab renders
- **THEN** its row shows the SeaTalk badge, Running and an inline Stop, and a session no conversation points at shows none

#### Scenario: the sessions list searches title and directory
- **GIVEN** an agent with sessions titled "Alpha rollout" and "Gamma", the second in `/work/alpha-api`
- **WHEN** the user types "alpha" in the search box
- **THEN** both rows are listed

#### Scenario: deleting a session asks first
- **GIVEN** a listed session
- **WHEN** the user chooses Delete… from its ⋯ menu
- **THEN** a confirmation says it is deleted from the agent and cannot be recovered, and nothing is deleted until the user confirms

#### Scenario: New conversation on the Sessions tab starts this agent
- **GIVEN** Codex's Sessions tab
- **WHEN** the user presses New conversation and confirms the dialog without changing it
- **THEN** the dialog had Codex chosen, and the daemon is asked to start a blank Codex session in the chosen directory
