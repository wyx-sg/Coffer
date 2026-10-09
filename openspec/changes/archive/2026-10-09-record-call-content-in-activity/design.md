## Context

The invocation log was deliberately metadata-only (ADR Audit and Retention, Option B
rejected) because a call's payload can carry code, customer data and secrets echoed by an
upstream. The owner now wants a reader to be able to tell what a call did, and agreed
(2026-10-09) to: content on by default with a per-machine switch, a 16 KB cut per part,
and no model-provider prompts or completions.

## Decisions

**Where content lives.** One nullable `content_json` column on `mcp_invocations`, a JSON
object with up to five parts (`arguments`, `result`, `error`, `request`, `response`), each
`{"text", "truncated", "bytes"}`. `text` is the part serialised as JSON (a cut part is a
prefix and no longer parses; the UI shows it as text). Lists defer the column; one call is
read by id. Retention is the table's own, unchanged.

**Redaction in three passes, two places.** The pure pass (domain `activity_content`) runs
in the gateway at capture time, where the injected values are known: the supervisor keeps
each live connection's secret overlay, and the HTTP custom-tool client masks its own
per-call headers before it hands the exchange up. It masks those values, credential
headers and secret-named fields, then cuts. The plaintext-detector pass runs in the
invocation writer (infrastructure, off the event loop) over every string leaf before the
row is inserted, so a token the agent pasted or an upstream invented is caught too.

Masking every value in the vault was considered and rejected: it would decrypt every
secret on every call, outside the per-destination approval boundary
([secret](../../specs/secret/spec.md) "Hold a secret for a new destination until a person
approves it"). An agent never holds a secret Coffer injected, so the values that can
reach a call's content are the ones injected into that upstream.

**Secret-named fields.** Matched on the whole name or its last `_`/`-` word, so
`max_tokens` and `token_count` are kept and `api_token`, `next_page_token` are masked;
only string values are masked.

**The custom-tool exchange.** The HTTP client already builds a masked diagnostic of each
response; it now also publishes the request and response of the call through a context
variable the gateway reads after `request()` returns (the call runs in the gateway's own
task), so no port changes shape.

**The switch.** `record_call_content` in `daemon-config.json`, read once and cached by a
small service the gateway sessions share; the route writes the file first, then the
cached value, then audits.

**Daemon log.** Audit details are already stored redacted, so the mirrored line may carry
them; cut at 2 KB so a large diff cannot flood the log. Call content never goes to the log.
