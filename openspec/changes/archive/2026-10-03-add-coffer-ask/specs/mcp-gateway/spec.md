## ADDED Requirements

### Requirement: Let an agent ask the owner a question during a Coffer turn
The gateway MUST offer the built-in tool `coffer__ask` to an MCP session whose
requests carry the `X-Coffer-Turn` token of a turn Coffer is running, and only to
such a session. Its input MUST take an optional markdown `context` and one to four
questions, each with a short `header`, the `question`, two to four options (a
`label` and an optional `description`) and `multi_select`. A call MUST raise the
question on that turn's conversation (spec chat "Pause a turn on a question for
the owner") and return only when every question is answered — with the chosen
labels and any free-text answer per question — or when the question is cancelled
or 24 hours pass, with a result saying no answer came. The shim MUST forward the
agent process's `COFFER_TURN_TOKEN` as `X-Coffer-Turn`, and the Codex
configuration Coffer writes for its `coffer` server MUST pass that variable
through and allow a tool call to run for 24 hours.

#### Scenario: an agent in a Coffer turn sees and calls coffer__ask
- **GIVEN** a turn Coffer runs, whose agent process has `COFFER_TURN_TOKEN` set
- **WHEN** the agent lists Coffer's tools and calls `coffer__ask` with one question and the options Yes and No
- **THEN** `coffer__ask` is in the list, and the call returns "Yes" once the owner answers Yes

#### Scenario: coffer__ask is not offered outside a Coffer turn
- **GIVEN** an agent session started in a terminal, with no turn token
- **WHEN** it lists Coffer's tools
- **THEN** `coffer__ask` is not among them, and a direct call is answered that asking works only inside a Coffer conversation
