## ADDED Requirements

### Requirement: Hand a failing MCP call's diagnosis to an agent
A call whose server never answered — it failed without the upstream returning a
result or a JSON-RPC error, or it timed out — MUST carry `handoff` on its
invocation record: one prompt naming the server, the tool, the error (passed
through the same secret scrub as a server's diagnosis), how many calls to that
server failed in the last 24 hours, the session and the call's id, and this
machine. Its steps MUST ask to find the cause and propose the fix before changing
anything, MUST forbid reading or changing the secrets Coffer stores, and MUST name
`coffer mcp test <name>`. It MUST NOT contain the call's arguments or result,
which Coffer never stores. A call that succeeded, a denied call and a call the
upstream answered with its own error carry no `handoff`.

#### Scenario: an unanswered call carries a hand-off without arguments
- **GIVEN** an errored call, a timed-out call, a successful call, a denied call and a call the upstream answered with an error result
- **WHEN** the invocations are read
- **THEN** the errored and timed-out calls carry a prompt naming the server, tool, error, session, call id and the count of the server's failures in the last 24 hours
- **AND** the other three carry none

### Requirement: Read every failed call at once
`GET /api/v1/mcp/invocations` MUST accept `status=failed` besides the four
outcomes, selecting every call that is not `ok` — an error, a timeout or a
denial — for the page and for its count.

#### Scenario: status failed is every outcome but ok
- **GIVEN** an ok, an errored, a timed-out and a denied call
- **WHEN** the invocations are read with `status=failed`
- **THEN** the errored, timed-out and denied calls are listed, and the total is three
