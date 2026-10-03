## ADDED Requirements

### Requirement: Pause a turn on a question for the owner
A question an agent raises in a turn — through `coffer__ask`, or through Claude
Code's own `AskUserQuestion`, which the Claude Code adapter MUST intercept before
it runs and turn into the same question — MUST be stored as a `question` block of
the reply that asked, with its context, its questions and options, and its state:
pending, answered (the answers, where they were given — the web page or a named
channel —, by whom and when) or cancelled. The turn MUST stay running while the
question is pending. The first answer MUST win: a later answer to a closed
question is refused with `QUESTION_CLOSED` and changes nothing. Stopping the turn,
the turn ending or the daemon shutting down MUST cancel a pending question, and
the agent is told no answer came. The answers MUST go back to the agent as the
tool's result; nothing is added to the conversation as the owner's message.

#### Scenario: AskUserQuestion waits for the owner and gets the answer
- **GIVEN** a Claude Code turn in a Coffer conversation
- **WHEN** Claude Code calls `AskUserQuestion` with the options "Yes" and "No", and the owner answers "Yes" on the Conversations page
- **THEN** the reply holds a question block that went from pending to answered "Yes" via the web page
- **AND** Claude Code receives "Yes" as its answer and carries on, and no user message was added

#### Scenario: the second answer to one question is refused
- **GIVEN** a question answered "Yes" in SeaTalk
- **WHEN** the web page sends the answer "No" for it
- **THEN** the request is refused with `QUESTION_CLOSED` and the answer stays "Yes"

#### Scenario: stopping a turn cancels its question
- **GIVEN** a turn waiting on a pending question
- **WHEN** the owner presses Stop
- **THEN** the question is cancelled and the agent is told the owner stopped the task

### Requirement: Answer a question in the conversation
While a reply waits on a question, its header MUST read "Waiting for you" and a
question card MUST sit at the end of the reply, above the reply box: the context
(markdown, a diff as a code block), each question with its options as equal
buttons — a single-choice tap answers, a multi-select question toggles its
options and sends them with Submit — with each option's description under its
label, and the line "Or reply with your answer.". Text sent from the reply box
while a question is pending MUST answer the first unanswered question instead of
queueing a message; the box's placeholder says so ("Reply, or answer with the
buttons above"). In a channel conversation the card notes it was also asked in
that chat. An answered question MUST collapse to one line, "✓ <question> ·
Answered: <answer> · HH:MM", adding "in <platform>" when it was answered in the
chat, and a cancelled one to "Not answered".

#### Scenario: a multi-select question is answered with Submit
- **GIVEN** a pending question with three options and multi-select on
- **WHEN** the owner toggles two options and presses Submit
- **THEN** the agent receives both labels, and the card collapses to one line naming them

#### Scenario: text typed while a question waits is the answer
- **GIVEN** a pending question
- **WHEN** the owner types "only on staging" and sends it
- **THEN** the question is answered with that text and no message is queued

### Requirement: Show which conversations wait on you
A conversation with a pending question MUST carry `needs_you` in the list, and its
row MUST show the status "Needs you" (warning colour) where a running one shows
"Running", in its usual place by time — no separate group or filter. The sidebar's
Conversations item MUST show a count of conversations with a pending question,
updated when a question is raised or closed.

#### Scenario: a waiting conversation is marked and counted
- **GIVEN** two conversations, one waiting on a question
- **WHEN** the Conversations page and the sidebar render
- **THEN** that row shows "Needs you", the other does not, and the Conversations item shows 1
- **AND** once the question is answered the status and the count go away
