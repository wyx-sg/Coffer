## ADDED Requirements

### Requirement: Preview a custom tool's request without sending it
The daemon MUST preview the request a custom tool would send — a saved tool with
`POST /api/v1/custom-tools/{name}/tools/{tool}/preview` and a draft with
`POST /api/v1/custom-tools/{name}/preview`, taking the same body as the matching
test — and `coffer custom-tool tool test` and `coffer custom-tool tool
test-draft` MUST offer `--dry-run`, which calls them. A preview MUST take a
test's own steps up to the request: the environment chosen by "Choose a custom
tool's environment on every call", the arguments checked by "Validate a custom
tool's arguments before any request", and the request built by the gateway's own
code ("Make a custom tool's request in the gateway"). It answers the chosen
environment, the method, the final URL, every header as it would be sent, the
rendered body, the timeout that applies and whose it is (the environment's own
or the group's), and the environment's variables. A secret header MUST carry
`***` in place of the credential (behind its scheme, `Bearer ***`), its secret's
id and name, its scheme and its state (`present`, `missing` or
`pending_approval`, read from the store's presence and the approvals, never from
the value). A preview MUST NOT read or decrypt any secret value and MUST NOT
make any HTTP request. It refuses what a call would refuse, with the same codes
and exit codes; a request that cannot be built in the chosen environment (a
`{env:NAME}` it does not define, a body template that is not JSON) is refused
with `CUSTOM_TOOL_REQUEST_INVALID` (422, exit `6`). With `--json` the command
prints the preview object as the route answers it.

#### Scenario: a dry run shows each environment's request without sending it
- **GIVEN** a group with environments `test` (the group's 30 s timeout, `region=eu-1`) and `live` (its own 7 s timeout, `region=us-1`), each with its own base URL, plain header and secret header, and a tool `POST /v1/{env:region}/search?cid={cid}` with a tool header and a body template
- **WHEN** the tool is previewed in `test` and in `live` with the same arguments
- **THEN** each answer names its environment, its own base URL with its region and the query filled, its own plain header, the tool header, the rendered body, and 30 s from the group or 7 s from the environment
- **AND** the upstream receives nothing, and no secret value is read

#### Scenario: a dry run names a secret header's secret but never its value
- **GIVEN** the same group, its secrets stored and approved
- **WHEN** the tool is previewed
- **THEN** `Authorization` reads `Bearer ***` with the secret's id, name, scheme `Bearer` and state `present`, and neither token appears anywhere in the answer

#### Scenario: a dry run refuses what a call would refuse
- **GIVEN** the same group
- **WHEN** a preview names no environment, then leaves out a required argument, then names `live` after it is switched off, then previews a draft whose path uses an `{env:NAME}` `test` does not define
- **THEN** the answers are `CUSTOM_TOOL_ENVIRONMENT_REQUIRED`, `CUSTOM_TOOL_ARGUMENTS_INVALID`, `CUSTOM_TOOL_ENVIRONMENT_DISABLED` and `CUSTOM_TOOL_REQUEST_INVALID`, each 422, and the upstream receives nothing

#### Scenario: a dry run on the command line prints the request and sends nothing
- **GIVEN** a group with environments `test` (a secret header waiting for approval) and `live`, and a saved tool `GET /status` with a plain header
- **WHEN** an agent runs `coffer custom-tool tool test <group> status --env test --dry-run --json`, the same in `live` without `--json`, the same with no `--env`, and `coffer custom-tool tool test-draft <group> --env live --dry-run` on a draft
- **THEN** the JSON names `test`, its URL and `Bearer ***` with the secret's name and `pending_approval`; the text names `live`, its URL and the plain header and says nothing was sent; the one with no environment exits `6` with `CUSTOM_TOOL_ENVIRONMENT_REQUIRED`; and the draft's URL is `live`'s
- **AND** the upstream receives nothing and no output carries the secret's value

### Requirement: Report what a custom tool's test reached
A test of a custom tool — saved, draft or of a group not saved yet — MUST
return, beside the status, URL, body and environment, the response headers that
help find the request on the API's side: `date`, `server`, `via`,
`retry-after` and the request and trace ids (`x-request-id`, `request-id`,
`x-correlation-id`, `x-trace-id`, `traceparent`, `x-b3-traceid`,
`x-amzn-requestid`, `x-amzn-trace-id`, `x-amz-request-id`, `x-amz-cf-id`,
`cf-ray`), names lower-cased, each value with the environment's secret values
masked and cut at 256 characters. Every other header — `set-cookie`,
`www-authenticate`, anything not on the list — MUST be left out. A test that got
no answer returns none. The command line prints them after the status, and the
Custom tools page shows them in the test's result. An agent's tool call is
unchanged.

#### Scenario: a test reports the request id but no cookie or credential
- **GIVEN** an environment with a secret header, and an API that answers `403` with an HTML body, `X-Request-Id`, an `X-Trace-Id` that contains the secret's value, `Set-Cookie`, `WWW-Authenticate` and an unknown header
- **WHEN** a draft tool is tested in that environment
- **THEN** the result carries `x-request-id`, `x-trace-id` with the value masked, `server` and `date`
- **AND** it carries no `set-cookie`, `www-authenticate` or unknown header, and neither the secret's value nor the cookie appears anywhere in it
