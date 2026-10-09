## Why

A custom tool's answer was judged by its HTTP status alone. Many APIs answer
`200` and say "failed" in a response header or a JSON field: a real gateway
answered `HTTP 200`, an empty body and an auth error code in a header, and the
agent received a successful result reading only `HTTP 200 OK` — the error code
was dropped with every header not on the built-in list. Nothing in the result,
the test or the invocation log could tell the call had failed.

## What Changes

- A group may carry **response settings**: extra response headers to report,
  and **response rules**. A rule reads one value — the HTTP status, a response
  header or a JSON Pointer into the body — and lists the values that mean
  success; it says what a missing value means and where the API's own error
  message is. Every rule must hold for a success. A tool may set its own rules,
  which replace the group's. With no rules an answer is judged by its HTTP
  status, as before. Coffer knows no API's convention: every name and value
  comes from the rules.
- A header that carries credentials or cookies can never be named, by a rule or
  as a diagnostic header; a rule is checked when the group or tool is saved.
- An agent's tool result names the headers the group asked to see (every
  diagnostic header when the call failed), says which rule failed with the value
  read and the API's message, and says `(empty body)` when there was none. A
  failed rule is an in-band tool error and an `error` invocation.
- A test reports the same judgement (`rule_failure`, `ok` false), the headers
  the group names or its rules read, and the body's size in bytes.
- `coffer custom-tool group create|update --response` and `tool add|update
  --response-rules` set them; `group show` and `tool test` print them; the
  Custom tools page edits and shows them.

## Impact

- Backend: `domain/mcp/http_api_response.py` (rules, judging), the tool outcome
  moves to `infrastructure/mcp/http_api_outcome.py`; group and tool wire models.
- CLI: `--response`, `--response-rules`; test and show output.
- Frontend: group response settings, a tool's rules, the test's rule failure.
- Specs: mcp-gateway, web-ui.
