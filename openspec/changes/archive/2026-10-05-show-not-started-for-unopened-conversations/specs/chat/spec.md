## MODIFIED Requirements

### Requirement: Open a conversation in the terminal
A row of the Conversations page MUST hand its session to the agent's own
interface: the main part of its split button **Open in
<terminal>** (named for the preferred terminal, e.g. **Open in iTerm**) MUST ask the
daemon to resume the session in the person's preferred terminal ([web-ui](../web-ui/spec.md)
"Let the user choose a terminal"; [daemon](../daemon/spec.md) "Open an agent session in a
terminal") — `claude --resume <session id>` for Claude Code and `codex resume <session id>` for
Codex, in the session's working directory. The split button's **▾** menu holds
**Open in <terminal>** for every other terminal on this machine — the system
terminal and each detected one — which opens the session there once and leaves the
preference as it is, then **Copy command**, which copies the same command line for
the person to run anywhere: the same shape as the hand-off button. A channel conversation
that has no native session yet — no turn has run on it — has nothing to open: in place of the
split button its row shows a muted **Not started**, whose tooltip says why, and it offers no
Copy command. An open the daemon refuses shows its
reason in a toast beside Copy command as the way out. Agent › Sessions rows use the same row and
the same behaviour. Pressing the row itself MUST NOT open a terminal or do anything else: only the split button opens a session ([agent-registry](../agent-registry/spec.md) "Open an agent's sessions from its Sessions tab").

#### Scenario: a row opens its session in the preferred terminal
- **GIVEN** a Claude Code session `abc-123` in `/work/api` and a preferred terminal
- **WHEN** the user presses the row, and then the main part of its split button
- **THEN** pressing the row asks the daemon for nothing, and the button asks it to open `claude --resume abc-123` in `/work/api` in that terminal, for the session's agent
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
- **THEN** it shows Not started instead of the split button, with a tooltip saying no turn has run so there is no session to open, and Copy command is not offered

#### Scenario: a refused open is reported with a way out
- **GIVEN** a daemon that refuses the terminal open
- **WHEN** the user presses a row
- **THEN** a toast shows the reason and offers Copy command
