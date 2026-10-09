## REMOVED Requirements

### Requirement: Record invocations without content
**Reason**: Calls now record their arguments and results, redacted and bounded.
**Migration**: Replaced by "Record invocations with redacted, bounded content"; rows recorded before keep no content.

## ADDED Requirements

### Requirement: Record invocations with redacted, bounded content
The system MUST record an invocation entry for every tool call, resource read, and prompt fetch — its target,
timestamp, duration and outcome. Each entry MUST also carry
its row `id`, and MUST name the agent whose session made the call (`agent_uid`) when that session reported one
on its handshake (see "Take the agent identity from the handshake"); a session that reported none writes
entries naming no agent, never a guessed one. A custom tool's call MUST also name the environment it was made
in (`environment`).

While call content recording is on ("Switch call content recording per machine"), the entry MUST also
carry the call's **content**: its `arguments` (a tool's or a prompt's arguments, a resource's uri), its
`result` (the coerced answer the agent received, an in-band `isError` result included), and its `error`
(the text of an exception the upstream raised or answered with, which the entry's `error_message` keeps
reducing to a Coffer-authored summary). A custom HTTP tool's call MUST also carry the `request` it sent
(method, final URL, headers and body) and the `response` it got (status, headers and body), and a Coffer
built-in tool's call carries its arguments and result like any other. A call refused before it reached an
upstream (`denied`) carries its arguments only.

Content MUST be redacted before it is written anywhere — the database, a log line, the wire — and in this
order: every value Coffer injected into that upstream for the call (a stdio or HTTP server's secret overlay,
a custom tool's resolved headers) is replaced with `••••••` wherever it appears; a header that carries
credentials (`Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`, `X-Api-Key`, `X-Auth-Token`
and any header whose name holds `token`, `secret`, `key` or `auth`) and the value of any field whose name
says it holds a secret (`password`, `passwd`, `secret`, `token`, `api_key`, `apikey`, `access_key`,
`private_key`, `client_secret`, `credential`, `authorization`, `cookie`, alone or as a name's last word)
is replaced whole; then every remaining string is scanned with the bundled plaintext-secret rules
([secret](../secret/spec.md) "Detect plaintext secrets with the bundled rules") and each finding replaced.
Each part (`arguments`, `result`, `error`, `request`, `response`) is serialised as JSON and MUST be cut at
16 KB (UTF-8), keeping the start; a cut part says so (`truncated: true`) and keeps its size before the cut
(`bytes`). Content is never written to `daemon.log`, and model-provider traffic is not a call here: its
prompts and completions are never recorded.

How long entries are kept, and the background pass that prunes them, are
[resource-framework](../resource-framework/spec.md) "Prune each registered log table on its own retention period" — the retention contract
every log-writing kind inherits — not this spec's own rule. This spec contributes `mcp_invocations` to that
registry with a 30-day default. The record is read per server
(`GET /api/v1/resources/mcp_server/{uid}/invocations`, `coffer log mcp --server <server>`) or across every
server (`GET /api/v1/mcp/invocations`, `coffer log mcp` with no server), the cross-server read
including Coffer's own built-in calls (`coffer`) and the rows of servers since deleted (their uid, with no name). Both HTTP reads
can be narrowed to one agent's calls with `agent_uid`. Both reads
page newest first by cursor ([resource-framework](../resource-framework/spec.md) "Page growing lists by an opaque cursor"),
and both CLI forms take `--status`, `--since`, `--limit`, `--cursor` and `--json`. A list carries no content;
one call is read with its content by `GET /api/v1/mcp/invocations/{id}` and `coffer log call <id>`
(404 `INVOCATION_NOT_FOUND`, exit `4`, for an id the log does not hold), whose `content` is `null` for a
call recorded while recording was off. One server's calls since a moment
(24 hours ago by default) are also read counted, for its page:
`GET /api/v1/resources/mcp_server/{uid}/invocations/summary` answers the calls, the errors (every call that
did not end `ok`) and the last call's time, per calling agent and per tool.

#### Scenario: invocation log records a call's arguments and result
- **GIVEN** content recording is on and an MCP client has called a tool with arguments `{"query": "coffer"}`
- **WHEN** the user lists the invocation log, then reads that call by its id
- **THEN** the list entry carries the timestamp, target capability, duration and outcome and no content
- **AND** the call read by id carries `arguments` `{"query": "coffer"}` and the result the client received

#### Scenario: an injected secret echoed by the upstream is masked in the record
- **GIVEN** a stdio server started with a secret injected into its environment, whose tool echoes that value in its result and in an error
- **WHEN** the tool is called twice, once succeeding and once raising, and both calls are read by id
- **THEN** the value appears in neither record, each place it stood reading `••••••`
- **AND** no file or table under `~/.coffer` holds the value

#### Scenario: secret-named fields and credential headers are masked whole
- **GIVEN** a call whose arguments hold `{"password": "hunter2-long", "max_tokens": 64, "headers": {"Authorization": "Bearer abc123def456"}}`
- **WHEN** the call is read by id
- **THEN** `password` and `Authorization` read `••••••` and `max_tokens` reads `64`

#### Scenario: a plaintext key the rules know is masked
- **GIVEN** a tool whose result holds a GitHub token in free text
- **WHEN** the call is read by id
- **THEN** the token reads `••••••` and the rest of the text is kept

#### Scenario: content past 16 KB is cut and says so
- **GIVEN** a tool whose result serialises to 40 KB
- **WHEN** the call is read by id
- **THEN** its `result` holds the first 16 KB with `truncated: true` and `bytes` of about 40 KB, and its `arguments` are whole

#### Scenario: a custom tool's call records its request and response
- **GIVEN** a custom-tool group whose `live` environment sends a secret `Authorization` header, and a tool whose API answers `200` with header `X-Sp-Error: 101` and body `{"error": "denied"}`
- **WHEN** an agent calls the tool in `live` and the call is read by id
- **THEN** `request` holds the method, the final URL, the headers with `Authorization` reading `••••••`, and the body
- **AND** `response` holds status `200`, the `X-Sp-Error` header and the body `{"error": "denied"}`

#### Scenario: a refused call records its arguments only
- **GIVEN** a tool switched off on its server
- **WHEN** an agent calls it with arguments and the call is read by id
- **THEN** the entry is `denied`, carries the arguments, and carries no result

#### Scenario: the command line reads the invocation log
- **GIVEN** a running daemon that has recorded invocations on two servers, on a Coffer built-in tool and on a deleted server
- **WHEN** the user runs `coffer log mcp --server <server>` and then `coffer log mcp --status error --json`
- **THEN** the first prints only that server's calls, newest first, each with its id
- **AND** the second prints, under `invocations`, only failed calls across every server, each naming its server, including `coffer` and the rows of a deleted server

#### Scenario: the command line reads one call with its content
- **GIVEN** a recorded call with arguments and a result, and an id the log does not hold
- **WHEN** the user runs `coffer log call <id>` for each
- **THEN** the first prints the call's metadata, then its arguments and result as indented JSON, a cut part marked as cut
- **AND** the second exits `4` saying no call has that id

#### Scenario: the invocation log pages by cursor
- **GIVEN** a server with three recorded invocations
- **WHEN** its invocations are read with `limit=2` and then with the answer's `next_cursor`
- **THEN** the first page holds the two newest calls and the second the oldest, with a `null` `next_cursor`

#### Scenario: a server's page reads its calls counted
- **GIVEN** a server with four calls in the last day — two by one agent, one of them failed, one by another agent and one by a session that reported none — and one older call
- **WHEN** `GET /api/v1/resources/mcp_server/{uid}/invocations/summary` is read
- **THEN** it answers four calls and one error, per agent 2/1, 1/0 and 1/0 for the session that reported none, and per tool the calls and errors of each tool
- **AND** the older call and another server's calls are not counted

#### Scenario: the invocation log names the calling agent
- **GIVEN** an agent's session connected through its shim made a call, and a session that reported no agent made another
- **WHEN** the invocation log is read, and read again with `agent_uid` set to that agent's uid
- **THEN** the first call's entry names that agent's uid and the second's names none
- **AND** the filtered read holds only the first call

#### Scenario: a custom tool's call names its environment in the log
- **GIVEN** a custom-tool group with the environments `test` and `live`
- **WHEN** an agent calls one of its tools in `live` and the invocation log is read
- **THEN** the entry names `live` as its environment and carries no credential

### Requirement: Switch call content recording per machine
Whether calls record their content MUST be one setting per machine, on by default, kept in
`~/.coffer/daemon-config.json` (`record_call_content`) and read with `GET /api/v1/settings/call-content`
and changed with `PUT /api/v1/settings/call-content` (`{"enabled": bool}`), and on the command line with
`coffer settings call-content show` and `coffer settings call-content set`. A change MUST take effect for
the next call in every session without a restart, MUST be audited (`call_content_recording_updated`,
naming the old and new value), and MUST NOT rewrite rows already recorded: turning recording off keeps
earlier content until retention prunes it, and turning it on records nothing for calls made while it was
off.

#### Scenario: recording is on by default and can be switched off
- **GIVEN** a fresh `~/.coffer` with no `record_call_content` setting
- **WHEN** the setting is read, an agent calls a tool, recording is switched off, and the agent calls it again
- **THEN** the setting reads on, the first call's record carries its content and the second's `content` is `null`
- **AND** the audit log holds `call_content_recording_updated` from on to off
