# Channel `/help` Is a List to Read, and a Card Carries Only the Buttons That Act on It

**Status**: Accepted
**Date**: 2026-10-20
**Deciders**: Yuxing Wu
**Related**: [Held Channel Messages Are Settled by Continue and Discard](held-channel-messages-are-continued-or-discarded.md), [Channel Switches: the Agent Opens a New Conversation, the Model Applies Next Turn](channel-switches-structural-vs-parametric.md), spec channels "List the commands with /help", "Report the chat's state as a status card", "Offer choices and actions as owner-gated cards"

## Context

The channel commands live on one roster (`domain/channel/commands.py`): `/new`,
`/stop`, `/status`, `/model`, `/dir`, `/resume`, `/thread`, `/del`, `/help`.
Until this decision `/help` was a card: the nine commands squeezed onto one
line joined by `·`, with no word on what each does, and under it a button per
command. Nine buttons do not fit a card (six at most, navigation included), so
the card was paged three ways with ← Prev / Next →. `/status` carried Stop, New,
Model, Resume and Dir, two of which have nothing to do with the state it shows.

The owner, looking at the SeaTalk help card on 2026-10-20: the card is a mess;
it should be one command per line with what it does; `/help` does not need
buttons; each command should carry only the buttons it needs; and review every
command for gaps or redundancy.

How comparable bots present help and buttons (their public docs, 2026-10):

- **Telegram's own guidance** ([bots/features](https://core.telegram.org/bots/features)):
  `/help` "returns a help message, like a short text about what your bot can do
  and a list of commands"; descriptions belong in the command menu
  (`setMyCommands`). Inline keyboards are for "changing settings, toggling
  options, navigating search results", placed under the message they act on.
- **claude-code-telegram** (RichardAtCT): commands as a plain list; only
  `/actions` carries buttons; even its repo list is text.
- **cc-connect** (chenhg5): commands grouped by area; on Feishu `/help` is a card
  with tabs, and buttons appear on the selection commands (`/list`, `/model`).
- **Slack apps**: `/app help` answers a list, one command per line with its
  description; buttons sit on the result of a specific action.

All agree that help is a list to read and that buttons belong to the message
they act on.

## Options Considered

### Option A — `/help` is text, one command per line; each card carries only its own actions (chosen)

`/help` answers a "Commands" heading, then `/<name> <args> — <description>` per
command (the same descriptions the Telegram menu registers), then "Anything else
goes to the agent as a message." A group's list has its four commands and says
the others work in a private chat. No buttons, so no paging. Each card keeps
only what acts on what it shows: `/status` keeps Stop (while running), Model and
Dir — the model and directory it names — and drops New and Resume; `/new` keeps
Agent, Model and Dir, the three settings the new conversation just opened with;
`/model` gains a Default option, as `/dir` already had one.

- Pros: readable at a glance, one line per command, on every platform; the
  descriptions cannot drift from the menu because both render from the roster;
  no paging on a list nobody browses; Telegram turns each `/command` in the text
  into a tap anyway. Every remaining button does something about the message it
  sits on.
- Cons: on SeaTalk, which has no command menu, a command is typed rather than
  tapped from `/help`. A user who remembered only `/status` no longer reaches
  New and Resume from it.

Wins because it is what the owner asked for and what every comparable bot does;
the lost shortcuts are commands one word long.

### Option B — Keep the help card, with one line per command above the buttons

Fix the text, keep a button per command.

- Pros: SeaTalk users can still tap a command from help.
- Cons: still nine buttons, so still three pages; the buttons repeat the text
  above them; the owner explicitly said help does not need buttons.

### Option C — A help card with only the most-used buttons (New, Stop, Status)

- Pros: fits one page; keeps a tap path on SeaTalk.
- Cons: an arbitrary subset that has to be maintained and argued; the list above
  already names the commands; still a button row the owner said was unneeded.

### Option D — Keep `/status` as the hub with every action

- Pros: one remembered word reaches every action (the previous rationale).
- Cons: buttons unrelated to what the card shows (New, Resume) are noise, against
  "each command carries only its own buttons"; `/help` now lists every command in
  readable form, which removes the hub's reason to exist.

## Command set reviewed

Every command was kept; none was added or merged:

- `/new [agent]` keeps the agent switch: another agent always means a new
  conversation (see the switches ADR), so a separate `/agent` would be a second
  way to do the same thing. cc-connect splits `/provider` from `/new` because it
  has providers *and* agents; Coffer has one dimension.
- `/resume [n]` both lists and picks, where cc-connect has `/list` + `/switch`.
- `/thread` needs no `/threads`: `/status` already lists the parallel threads.
- `/del` stays beside the 🗑 button: 🗑 rides only group replies, so a direct
  chat and a platform without buttons have only `/del`.
- Commands other bridges add are not needed: `/mode` (permissions are Coffer's
  approval cards), `/provider` (connections are set in Coffer), `/cron`,
  `/usage`; an agent's own slash commands (`/compact`, `/cost`) already pass
  through to it.

The one gap found — no way to drop the messages a `/stop` held — is its own
decision: [Held Channel Messages Are Settled by Continue and Discard](held-channel-messages-are-continued-or-discarded.md).

## Decision

`/help` is text rendered from the roster (`help_text`), one line per command with
its description, and carries no buttons (`status_card.cmd_help`). The help card
and its `help` page kind are removed. `/status` carries Stop while a turn runs,
Continue and Discard while messages are on hold, then Model and Dir
(`command_cards.STATUS_ACTIONS`). The `/model` card's first option is Default
(`selection_cards.model_card`), first so that a chat on the default opens the
card on page one with its tick in view. The roster's order is new, stop, status,
model, dir, resume, thread, del, help, and its descriptions are rewritten to
read as a sentence after the dash.

## Consequences

- Pairing ends with the command list as text instead of a card.
- The Telegram menu descriptions change with the roster (both languages).
- A test that counted model-card buttons now counts the Default option too.
- The design canvases show the help as text and the slimmer status card.
