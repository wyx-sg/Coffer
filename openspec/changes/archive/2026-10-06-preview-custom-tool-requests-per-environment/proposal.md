## Why

A custom-tool group can have several environments, but the tool form still read its URL
help, headers, secret note and timeout from the group's compatibility fields — the first
environment — while the Test picker kept a choice of its own. Picking a second environment
changed where Run went and nothing else on the form. Agents debugging a failing tool from the
command line also had no way to see the request a call sends (its final URL and headers)
without sending it, and a test's result carried no request id to quote to the API's owners.

## What Changes

- The daemon previews a tool's request without sending it — saved or draft — through the
  same environment choice, argument check and request building a call uses, with each secret
  header shown by its secret's id, name, scheme and state and `***` for its value; no secret
  value is read and no request is made. `coffer custom-tool tool test` and `test-draft` take
  `--dry-run`.
- A test returns the allow-listed response headers (request and trace ids, `server`, `date`,
  `via`, `retry-after`), masked; cookies, auth challenges and unknown headers are left out.
- The tool drawer and Add request into an existing group hold one chosen environment: the
  request help, the headers already added, a request preview (URL, merged headers, secret and
  its state, variables, effective timeout) and Run all follow it; picking saves nothing; an
  environment switched off or deleted while the form is open is reported and never replaced.
- The group list counts a group's environments instead of naming the first one's host, and
  the page's copy describes a group as holding environments.

## Impact

- Backend: request building moves to the domain (`http_api_request.py`) so the gateway, a
  test and a preview share it; new preview routes; `response_headers` on test results.
- CLI: `--dry-run` on `custom-tool tool test` and `test-draft`.
- Frontend: tool form environment state, request preview, response headers, group row copy.
- Specs: mcp-gateway, web-ui.
