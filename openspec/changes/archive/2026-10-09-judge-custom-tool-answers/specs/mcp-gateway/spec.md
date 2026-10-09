## ADDED Requirements

### Requirement: Judge a custom tool's answer by its group's response rules
A custom-tool group MUST carry **response rules** that decide whether an answer
the API gave is a success, and a tool MAY carry its own, which replace the
group's as a whole (an empty list judges the tool by its HTTP status alone; no
list follows the group). A rule MUST read one value of the answer — the HTTP
status, one response header (by name, case-insensitive) or one field of a JSON
body (by a JSON Pointer such as `/code` or `/error/0/code`) — and MUST list the
values that mean success (1 to 20, compared as text: a JSON string as it is, a
number as written with `0.0` read as `0`, `true`, `false` and `null` as those
words, an object or array as compact JSON). A rule MUST say what an answer
without the value means — success (the default) or failure — and a JSON field
is missing when the pointer names nothing, the body is not JSON, or the body was
cut at 1 MiB. A rule MAY name where the API puts its own error message: a
response header or a JSON Pointer. An answer MUST be a success only when its
status is below 400 and every rule holds; a group without rules is judged by its
status alone, so an empty `200` or a `204` is a success and no field of a JSON
body is read. A failed rule MUST make the agent's result an in-band tool error
that names the rule, the value read (or that it was missing), the success values
and the message, masked and cut at 256 characters, and the call MUST be recorded
as `error`. A test MUST judge the answer the same way, returning `ok` false and
the failed rule. The judgement MUST know no API's convention: no header name,
field or code is built in, and an API's convention is expressed only as rules. A
group or tool whose rule is malformed — more than 10 rules, no success value, a
status rule naming a header or a non-status value, a header rule naming a
credential or cookie header ("Report what a custom tool's test reached"), a JSON
rule whose name is not a JSON Pointer — MUST be refused when it is saved, with
nothing persisted. The group's rules and diagnostic headers MUST be read and set
through the group's routes and `coffer custom-tool group create|update
--response`, a tool's through the tool's routes and `coffer custom-tool tool
add|update --response-rules`, and on the Custom tools page.

#### Scenario: an answer with no response rules is judged by its status
- **GIVEN** a group with no response rules, and an API that answers `200` with an empty body to one tool and `200` with `{"code": 7}` to another
- **WHEN** an agent calls each
- **THEN** both are successes recorded `ok`, the first result reads `HTTP 200 OK` and `(empty body)`, and the second carries the body

#### Scenario: a header rule turns a 200 into an error with the API's message
- **GIVEN** a group whose rule reads the header `X-Result-Code`, takes `OK` as success and reads its message from `X-Result-Text`
- **WHEN** the API answers `200` with an empty body, `X-Result-Code: DENIED` and `X-Result-Text: quota exhausted`, and then `200` with `X-Result-Code: OK` and a body
- **THEN** the first result is an in-band error naming `x-result-code`, `DENIED`, the success value `OK` and `quota exhausted`, recorded `error`
- **AND** the second is a success recorded `ok` that carries the body

#### Scenario: a JSON field rule judges the body and a missing field follows the rule
- **GIVEN** a tool whose own rule reads `/status/code`, takes `0` as success, counts a missing field as failure and reads its message from `/status/message`
- **WHEN** the API answers `{"status": {"code": 0}}`, then `{"status": {"code": 3, "message": "not found"}}`, then a body that is not JSON
- **THEN** the first is a success, the second an error naming `/status/code`, `3` and `not found`, and the third an error saying the field is missing

#### Scenario: a tool's own rules replace its group's
- **GIVEN** a group whose rule fails every answer without the header `X-Result-Code`, and two tools of it: one following the group, one with its own empty list of rules
- **WHEN** an agent calls both against an API that sends no such header
- **THEN** the first is an error and the second a success

#### Scenario: a malformed response rule is refused
- **GIVEN** a group
- **WHEN** a change sets a header rule on `Authorization`, a JSON rule named `code` with no leading `/`, a status rule with the success value `OK`, or a rule with no success value
- **THEN** each change is refused as a validation error and the group is unchanged

#### Scenario: a test, the command line and the agent judge an answer alike
- **GIVEN** a group whose rule reads the header `X-Result-Code` with the success value `OK`, and an API answering `200`, an empty body and `X-Result-Code: DENIED`
- **WHEN** the tool is tested on its route, with `coffer custom-tool tool test --json`, and called by an agent
- **THEN** the test answers `ok` false, `body_bytes` 0, the failed rule and `x-result-code` among its headers; the command prints the same and exits `7`; and the agent's result is an in-band error recorded `error`

#### Scenario: an API's error header convention is a rule the group declares
- **GIVEN** a group shaped like an RPC gateway that answers every call `200` and puts its error code in `X-Sp-Error` and its text in `X-Sp-Errmsg`, with the rule: header `x-sp-error`, success `0`, a missing header a success, message from `x-sp-errmsg`
- **WHEN** the API answers `200`, an empty body, `X-Sp-Error: 101` and `X-Sp-Errmsg: ERROR_SP_NEED_AUTH`, then `200`, `X-Sp-Error: 0`, `X-Sp-Errmsg: SUCCESS` and a JSON body
- **THEN** the first result is an in-band error naming `101` and `ERROR_SP_NEED_AUTH`, recorded `error`, and the second a success carrying the body
- **AND** the same group with no rules judges both answers a success

## MODIFIED Requirements

### Requirement: Make a custom tool's request in the gateway
On `tools/call` for a custom tool the gateway MUST resolve the call's
environment ("Choose a custom tool's environment on every call"), validate the
arguments ("Validate a custom tool's arguments before any request"), and render
the request from the arguments and that environment — the environment's base
URL; each path hole percent-encoded so a value cannot change the path, the query
or the host; each `{env:NAME}` filled with the environment's variable; a query
pair whose hole's argument is absent dropped; the body template filled with JSON
values, or, with no template, the unused arguments sent as a JSON object for
POST, PUT and PATCH — add the environment's secret headers with each secret's
value last, send it with the environment's timeout (the group's when it sets
none) without following redirects, read at most 1 MiB of the response, and
return one text result that starts with the HTTP status line. A status of 400 or
more MUST be returned as an in-band tool error, and so MUST an answer that
breaks one of the tool's response rules ("Judge a custom tool's answer by its
group's response rules"); a redirect MUST be returned, not followed; a timeout
MUST be recorded as `timeout`. After the status line the result MUST name the
response headers the group asks to see ("Report what a custom tool's test
reached") — every reported header when the call failed — then the broken rule,
if any, and then the body, or `(empty body)` when the answer had none. The secret's value MUST NOT
appear in the result, the tool's description or schema, or any log, invocation
or audit record: an occurrence in the response is masked as `***`. Every call
MUST be recorded like any other tool call ("Record invocations without
content"), naming its environment.

#### Scenario: a custom tool call sends the rendered request with the secret
- **GIVEN** a group with base URL `https://api.example/v2`, an `Authorization` header bound to an approved secret holding `<token>` with the scheme `Bearer`, and a tool `GET /invoices/{id}?status={status}`
- **WHEN** an agent calls it with `id` = `a/b` and no `status`
- **THEN** the gateway sends `GET https://api.example/v2/invoices/a%2Fb` with `Authorization: Bearer <secret>`
- **AND** the agent receives `HTTP 200 OK` and the body, and the invocation log records one `ok` call with no arguments or content

#### Scenario: a custom tool's response is capped and masked
- **GIVEN** an upstream that answers with a 2 MiB body containing the secret's value
- **WHEN** an agent calls the tool
- **THEN** the result holds at most 1 MiB of the body, says it was truncated, and shows `***` where the secret's value was

#### Scenario: an error status is an error result and a redirect is not followed
- **GIVEN** one tool whose upstream answers 404 and one whose upstream answers 302 to another host
- **WHEN** an agent calls each
- **THEN** the first result is an in-band error starting `HTTP 404`, recorded as `error`
- **AND** the second result reports the 302 and its location, and no request reaches the other host

### Requirement: Report what a custom tool's test reached
A test of a custom tool — saved, draft or of a group not saved yet — MUST
return, beside the status, URL, body and environment, the response headers that
help find the request on the API's side: `date`, `server`, `via`,
`retry-after` and the request and trace ids (`x-request-id`, `request-id`,
`x-correlation-id`, `x-trace-id`, `traceparent`, `x-b3-traceid`,
`x-amzn-requestid`, `x-amzn-trace-id`, `x-amz-request-id`, `x-amz-cf-id`,
`cf-ray`), names lower-cased, each value with the environment's secret values
masked and cut at 256 characters. A group MAY name further headers to report
(its **diagnostic headers**, at most 20), and every header a response rule reads
is reported too; a header that carries credentials or cookies
(`authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `set-cookie2`,
`www-authenticate`, `proxy-authenticate`, `x-api-key`, `api-key`) MUST be
refused when it is named and MUST never be reported. Every other header — a
cookie, an auth challenge, anything neither listed nor named — MUST be left out.
A test MUST also return the number of body bytes read. A test that got no answer
returns no headers. The command line prints them after the status, and the
Custom tools page shows them in the test's result. An agent's tool result names
the group's diagnostic headers and the headers its rules read, and every
reported header when the call failed.

#### Scenario: a test reports the request id but no cookie or credential
- **GIVEN** an environment with a secret header, and an API that answers `403` with an HTML body, `X-Request-Id`, an `X-Trace-Id` that contains the secret's value, `Set-Cookie`, `WWW-Authenticate` and an unknown header
- **WHEN** a draft tool is tested in that environment
- **THEN** the result carries `x-request-id`, `x-trace-id` with the value masked, `server` and `date`
- **AND** it carries no `set-cookie`, `www-authenticate` or unknown header, and neither the secret's value nor the cookie appears anywhere in it

#### Scenario: a group's named headers reach the agent and a credential header cannot be named
- **GIVEN** a group whose diagnostic headers name `X-Backend-Region`, and an API that answers `200` with `X-Backend-Region`, `Server` and a JSON body
- **WHEN** an agent calls a tool, and a person then tries to add `Set-Cookie` to the group's diagnostic headers
- **THEN** the agent's result names `x-backend-region` and not `server`, and a test reports both
- **AND** the change naming `Set-Cookie` is refused as a validation error, and the group is unchanged

### Requirement: Manage custom tools from the command line
Every custom-tool operation of the Custom tools page MUST be available as a
`coffer custom-tool` command that calls the same REST route: list, show, create,
update and delete a group; enable and disable it; set its reach; add, show,
update, enable, disable and delete a tool, including its method, path, headers,
body template, argument schema, `changes_data` (a read-only `POST` may set
`changes_data=false`) and its own response rules; set a group's response
settings; add, update, rename, enable, disable and delete an
environment and bind a secret to one of its headers; test a draft tool and a
saved tool in a chosen environment; read an OpenAPI document; and preview and
apply a re-import. A tool's definition, request template and schema MUST be
accepted from flags, a file (`--data @file`) or standard input (`--data -`).
Every command MUST offer `--json` and the exit codes of [resource-framework]
"Offer every management operation on the command line". A command whose change
leaves a secret approval pending MUST print the approval ids and the command
that approves them, and exit `9`. The commands are a client of the REST routes:
no script, local HTTP adapter, proxy or MCP wrapper takes part, and the gateway
calls the upstream API itself.

#### Scenario: a group is configured end to end from the command line
- **GIVEN** a running daemon, a stored secret `billing-test-token` and an HTTP API answering on two base URLs
- **WHEN** an agent runs, one command at a time, `coffer custom-tool group create billing --env test=https://test.billing.example`, `coffer custom-tool env add billing live --base-url https://billing.example`, `coffer custom-tool env set-header billing test Authorization --secret billing-test-token --scheme Bearer`, `coffer custom-tool tool add billing --data @search.json` (a `POST /search` with `changes_data` false), `coffer custom-tool group reach billing --agent claude-code`, and `coffer custom-tool tool test billing search --env test --args '{"q":"x"}' --json`
- **THEN** each command exits `0` except a binding that waits for approval, which prints its approval id and `coffer approval approve <id>` and exits `9`
- **AND** the group, its two environments, the tool with `changes_data` false and the reach are what the Custom tools page shows, and the test's JSON carries the upstream's status line and the environment's actual target

#### Scenario: a change made on the page is read back by the command line
- **GIVEN** a group created with `coffer custom-tool group create`
- **WHEN** a person renames one of its environments and switches a tool off on the Custom tools page, and an agent runs `coffer custom-tool group show <group> --json`
- **THEN** the JSON carries the renamed environment and the tool switched off

#### Scenario: an OpenAPI document is imported and re-imported from the command line
- **GIVEN** an OpenAPI file with three operations
- **WHEN** an agent runs `coffer custom-tool import read --file openapi.yaml --json`, creates a group from two operations with `coffer custom-tool group create --from-openapi openapi.yaml --operation <op> --operation <op>`, and later runs `coffer custom-tool reimport preview <group> --file openapi.yaml` and `coffer custom-tool reimport apply <group> --file openapi.yaml --add <op>`
- **THEN** the read lists three draft tools, the group holds two, the preview names the one to add and changes nothing, and the apply adds it keeping every environment
