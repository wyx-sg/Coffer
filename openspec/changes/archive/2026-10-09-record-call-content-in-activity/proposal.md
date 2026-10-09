## Why

Activity is too terse to tell what actually happened. A tool call reads as "who
called which tool, how long it took and whether it worked": its arguments and its
result are never kept, so a failed or surprising call cannot be understood after
the fact — an HTTP custom tool that answered `200` with an error header looked
like a success and nothing showed why. Changes and daemon log lines have the same
problem one level down: several audit events carry no facts beyond their name,
and the daemon log mirrors an event without any of its details.

## What Changes

- **Tool calls keep their content.** Every call through the gateway — MCP tools,
  resource reads and prompt fetches, Coffer's own built-in tools and custom HTTP
  tools — records its arguments and its result (or the upstream's error text),
  redacted and bounded. A custom HTTP tool also records the request it sent
  (method, URL, headers, body) and the response it got (status, headers, body).
- **Redaction before anything is written.** The values injected into that
  upstream are replaced with `••••••`; auth-carrying headers (Authorization,
  Cookie, X-Api-Key, …) and the values of secret-named fields (password, token,
  secret, api_key, …) are masked whole; the bundled plaintext-secret rules run
  over every string as a last pass. No secret value reaches the database or a log.
- **Bounded.** Each recorded part is cut at 16 KB and says so, with its original
  size. The 30-day tool-call retention is unchanged.
- **A switch, on by default.** Settings › Data › History gains *Record tool call
  content*; off records metadata only, as before. Changing it is audited.
  `coffer settings call-content show|set`.
- **Read on demand.** Lists stay metadata-only; `GET /api/v1/mcp/invocations/{id}`
  answers one call with its content, and the Activity drawer shows Arguments,
  Result, Request and Response as foldable, copyable JSON with a cut marker.
  `coffer log call <id>` prints the same.
- **Changes say what changed.** Audit events that carried no facts gain them
  (from → to, what was affected, counts), knowledge and vault text edits carry a
  unified diff capped at 8 KB, and each audited event's details are mirrored into
  the daemon log line, capped at 2 KB.
- **Model-provider traffic is unchanged:** prompts and completions are never
  recorded; usage stays metadata only.

## Impact

- Specs: mcp-gateway ("Record invocations without content" becomes "Record
  invocations with redacted, bounded content"; new "Switch call content recording
  per machine"), resource-framework ("Audit every lifecycle change"), web-ui
  (Activity drawer, Data › History).
- Backend: `mcp_invocations.content_json` (migration), a pure redaction/cut module
  in the domain, capture in the gateway, built-in tools and the HTTP custom-tool
  client, scrub with the plaintext detector in the invocation writer, the setting
  in `daemon-config.json`, the detail and setting routes, audit details.
- CLI: `coffer log call`, `coffer settings call-content`.
- Frontend: call drawer content sections, History switch, i18n.
- Docs: Activity guide, observability, MCP gateway architecture, CLI reference
  (en + zh); a new ADR superseding the "metadata only" part of Audit and Retention.
- Canvases: System (Activity call drawer) and Shell (Settings › Data).
