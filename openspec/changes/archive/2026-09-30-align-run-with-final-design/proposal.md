## Why

The final design of the Run canvas (Conversations and Channels) settled a few
channel behaviours the code did not have yet, and redrew several surfaces the
code already had: a busy chat is told its place in the queue, `/new` answers
with a one-line card, a channel is named by any display name, and a channel's
Settings gain Replies and Working directories sections in the board's order.

## What Changes

- A message that waits behind a running turn is answered "⏳ Queued (n)"; only
  one arriving with ten already waiting is dropped, and the chat is told why.
- `/new` answers with a one-line card — agent · model · directory — with Agent,
  Model and Dir buttons; Agent opens an agent card whose tap does what
  `/new <agent>` does.
- `/status` reads as the conversation's title, one settings line, the state and
  the parallel threads, with Stop only while a turn runs; `/help` is the roster
  on one line with New, Stop, Model, Status and Resume; `/dir` names paths with
  `~` and folds the channel's default directory into its card.
- A channel's default working directory is a setting of its own: the Default in
  Settings › Working directories, and `coffer channel add|edit --default-dir`
  (`edit --no-default-dir` clears it). The allowed list is edited as rows.
- A channel is named by any display name: the Add dialog registers it as the
  title and derives the resource name; Settings edit it as the channel's Name.
- The Channels page follows the boards: Settings in the board's order with
  inline hints, the overview's command hint names `/new <agent>`, and the ⋯
  menu reads Replace app secret… / Replace bot token… and Delete channel….
- The Conversations page follows the boards (see the `chat` delta).

## Impact

- Specs: `channels` (queue notice, `/new` card and agent card, status and help
  cards, working directories, display names), `chat` (the page's board
  alignment).
- Code: `backend/coffer/application/channel/` (turn driver, command cards,
  `/dir`, `/status`, `/help`), `backend/coffer/surfaces/cli/` (channel options),
  `frontend/src/components/channel/`, `frontend/src/components/chat/`.
- Docs: the channels guide and the coffer-guide skill's channel commands.
