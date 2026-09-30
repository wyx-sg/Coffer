## ADDED Requirements

### Requirement: Test an unsaved server config before adding it
The daemon MUST test an MCP server config that is not registered, so the Add dialog can show what a server offers before Add server: a stdio server is started for the length of the test and an HTTP one is connected to, MCP `initialize` and `tools/list` run (and the resource and prompt counts are read when the server declares them), the newest stderr lines are kept, and everything is then discarded. The test MUST persist nothing — no resource, no health record, no invocation record, no audit event. A URL typed into the form MUST pass the SSRF guard before any request, and a redirect MUST NOT lead the test to another origin. A config citing a stored secret MUST NOT be started, because a stored secret is released only to a registered destination whose binding a person approved; values typed into the form's secret rows apply to this test only and MUST NOT be stored, logged, audited or echoed — every typed secret value is redacted from the stderr tail and the error message. The whole test MUST end within a hard time limit (30 seconds, the config's own timeouts capped by it), and a stdio server's whole process group MUST be stopped when the test ends, whether it passed, failed, ran out of time or its caller went away. A failed test names its cause with a stable code: `url_refused`, `spawn_failed`, `exited` (with the exit code), `timeout`, `initialize_failed`, `connect_failed` or `stored_secret_not_released`.

#### Scenario: a stdio config is tested without saving anything
- **GIVEN** the daemon is running and no MCP server is registered
- **WHEN** the Add dialog tests a stdio config whose server offers two tools, one resource and one prompt
- **THEN** the result is a pass naming both tools with a count of one resource and one prompt
- **AND** no resource, health record, invocation record or audit event exists afterwards

#### Scenario: a typed private URL is refused before any request
- **GIVEN** the daemon is running
- **WHEN** the Add dialog tests an HTTP config whose URL names a loopback address
- **THEN** the result is a failure with code `url_refused` saying that a server there is tested once it is added, and no request was made to that address

#### Scenario: a config citing a stored secret is not started
- **GIVEN** the daemon is running
- **WHEN** the Add dialog tests a stdio config whose environment cites a stored secret
- **THEN** the result is a failure with code `stored_secret_not_released` naming the key, and no process was started

#### Scenario: a failed test shows the exit code and the redacted stderr tail
- **GIVEN** a stdio config whose command prints the secret typed into the form on stderr and exits with status 3
- **WHEN** the Add dialog tests it with that secret typed in
- **THEN** the result is a failure with code `exited` and exit code 3, and its stderr tail shows the line with the secret redacted

#### Scenario: a test past its time limit stops the server's whole process group
- **GIVEN** a stdio server that forks a child and never completes `initialize`
- **WHEN** the test runs past its time limit
- **THEN** the result is a failure with code `timeout`, and neither the server nor the child it forked is still running

### Requirement: Report what a test of a registered server found
A test of a registered MCP server MUST report what the unsaved-config test reports — the tools found with their count, the resource and prompt counts, the redacted stderr tail, the failure code and the exit code — run by the same probe, with the server's stored secrets released per its approved binding and its whole process group stopped when the test ends. It MUST still record the outcome as the server's health.

#### Scenario: a registered server's test lists its tools and records its health
- **GIVEN** a registered stdio server offering two tools
- **WHEN** the user tests it
- **THEN** the result is a pass naming both tools, and the server's status reads healthy

### Requirement: Describe the built-in coffer server
The daemon MUST describe Coffer's own `coffer` MCP server read-only, so the MCP servers page can show it beside the servers the person added: its name, its transport (Streamable HTTP), the endpoint URL agents connect to on the bound port, that it is healthy while the daemon answers, that it reaches every connected agent (with the uids of the agents connected now), its tools from the gateway's built-in tool list as agents see them (only the tools of switched-on features, each with its `coffer__` name), and the last 24 hours of its calls in the shape a registered server's page reads. It is not a registered resource: it has no row, and nothing about it can be edited or removed.

#### Scenario: the built-in coffer server is described read-only
- **GIVEN** the daemon is running with one agent connected and a built-in tool called once
- **WHEN** the MCP servers page reads the built-in server
- **THEN** it is named `coffer` with the endpoint `http://127.0.0.1:<port>/mcp`, reaches that agent, lists `search_tools` as `coffer__search_tools`, and counts the one call
- **AND** no `mcp_server` resource named `coffer` exists

### Requirement: Read a server's capability list from its saved switches
The capability list of one MCP server MUST also be readable from its saved switches alone, without reaching the server, so the page of a server that is failing, off or missing its launcher or secret shows its tools at once instead of waiting out the discovery timeout. That read MUST say it came from the saved switches (`from_cache`), and a server that never listed anything MUST read as empty lists rather than an error.

#### Scenario: the saved-switches read answers without reaching the server
- **GIVEN** a registered MCP server whose tools were listed once, and a discovery that would fail if asked
- **WHEN** the page reads its capability list from the saved switches
- **THEN** the answer lists those tools from the saved switches without asking the server, and a server never listed reads as empty lists

### Requirement: Test a custom tool request before its group is saved
The daemon MUST run a request of a custom-tool group that is not saved yet — its base URL, headers and timeout given inline with the draft tool and sample arguments — once, and return what came back in the same shape as a saved group's test, saving nothing and logging no invocation. No stored secret is sent: an unsaved group has no approved binding, so the request goes without its auth header. Its base URL was typed into a form, so it MUST pass the SSRF guard before anything is sent (Principles → Network defaults); a refused address is reported as not tested. Every test result — saved group or not — MUST say how a request failed when no answer came back: the request could not be built, it timed out, it could not connect, or its address was refused.

#### Scenario: a request of an unsaved group is tested without its secret
- **GIVEN** no group exists and an HTTP API answering on a public address
- **WHEN** a draft request with a base URL, a header and sample arguments is tested
- **THEN** the API receives the request with that header and no auth header, the answer's status and body come back, and still no group exists

#### Scenario: an unsaved group on a private address is not tested
- **GIVEN** a draft request whose base URL resolves to a loopback address
- **WHEN** it is tested before the group is saved
- **THEN** nothing is sent and the result says the address was refused

#### Scenario: a failed test says how it failed
- **GIVEN** a draft request whose base URL has nothing listening, and one whose path names an argument it does not declare
- **WHEN** each is tested
- **THEN** the first reports it could not connect and the second that the request could not be built, while a request the API answers reports no failure

### Requirement: List what a re-import changes in the tools it keeps
A re-import's preview MUST name, besides the operations it would add and the tools it would remove, every kept tool whose operation the spec now describes differently — an argument it now requires, or a changed method, path or body template — and an OpenAPI reading MUST carry each operation's first tag, so the import form can group operations by it.

#### Scenario: a re-import preview names the tools the spec changed
- **GIVEN** a group imported from a spec whose `POST /invoices` took no arguments
- **WHEN** the spec now requires a `currency` query argument there and the group is previewed for re-import
- **THEN** the preview names `create_invoice` as changed with the new required argument `currency`, and the group's tools are unchanged
