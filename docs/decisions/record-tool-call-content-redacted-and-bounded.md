# Record Tool Call Content, Masked Where the Secrets Are Known and Cut at 16 KB

**Status**: Accepted
**Date**: 2026-10-09
**Deciders**: Yuxing Wu
**Related**: [Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table](audit-and-retention.md),
[Evals: Opt-In Capture, Hand Curation, and a Deterministic Regression Gate](eval-capture-and-regression-gate.md),
[Only a Present Human Sees a Secret or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md),
spec mcp-gateway "Record invocations with redacted, bounded content",
spec mcp-gateway "Switch call content recording per machine",
spec web-ui "Filter each Activity tab and expand any row",
architecture [observability](../../docs-site/architecture/observability.md#call-content)

## Context

The invocation log (`mcp_invocations`) recorded, for every call an agent made
through the gateway, which capability ran, when, for how long and with what
status, and nothing the call carried. Error text from the upstream was replaced
by a fixed Coffer-authored marker. The reason was sound: arguments and results
carry file contents, query results and tokens an upstream echoes back, and the
log is kept for 30 days in plaintext SQLite and is readable through
`coffer log`.

In use, the record was too thin to answer the question people open it with:
*what did that call actually do?* A failed custom HTTP tool showed `error` with
`upstream tool returned an error result (isError)` and no request, status or
body. A "successful" call that returned the wrong thing looked identical to one
that returned the right thing. The only way to find out was to reproduce the
call by hand, which for an agent's call from an hour ago is often impossible.

The forces:

- **Secrets must never be logged.** This is the line the previous design held
  by recording nothing.
- **Plaintext exists only at the moment of use.** Secrets are envelope-encrypted
  in the vault and released per destination after a person approves it
  ([Only a Present Human Sees a Secret or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md)).
  Whatever masks secrets must not widen who decrypts what.
- **Size.** A tool can return megabytes (a file read, a search dump); the log
  is one SQLite file on the user's machine.
- **The person decides.** Some people will not want any payload kept, whatever
  the masking.

## Options Considered

### Option A — Record content, masked where the secrets are known, cut at 16 KB, switchable per machine (chosen)

Each row gains a `content` object with up to five parts: `arguments`,
`result`, `error`, and for a custom HTTP tool the `request` (method, URL,
headers, body) and `response` (status, headers, body). Each part is
`{text, truncated, bytes}`.

Masking runs before the row is written, in two layers:

1. **In the gateway**, which knows exactly which secrets this call could carry.
   The supervisor remembers the values it injected into each upstream's
   environment or headers, and a custom tool masks the credentials it added to
   that one request. Those values are replaced with `••••••` wherever they
   appear, including in an upstream's echo. Credential headers (`Authorization`,
   `Cookie`, `X-Api-Key`, any header naming a token, secret, key or auth) and
   JSON fields whose name says secret (`password`, `token`, `api_key`,
   `client_secret`…) are masked whole, whatever their value.
2. **In the writer**, as a backstop for a secret the call carried that Coffer
   did not inject (a token the agent pasted into an argument): every part runs
   through the bundled gitleaks rules that already find plaintext keys in the
   vault and before a sync push.

Each part is then cut at 16 KB, and says how big it was. Recording is on by
default; `record_call_content` in `~/.coffer/daemon-config.json` (Settings ›
Data › History, `coffer settings call-content`) switches it per machine, and
the switch is audited. List routes omit `content`; one call is read with it by
id. Content never goes to `daemon.log`. The fixed `error_message` markers stay,
so the server status logic that tells a failing tool from a failing server is
unchanged.

Pros: a reader sees what each call did, without reproducing it; masking uses
exactly the secrets the call carried, so it adds no decryption; field, header
and rule masking catch the common leaks that value matching cannot; the cut
bounds growth at roughly 80 KB per call worst case, inside the existing 30-day
retention; a person who wants none of it turns it off. Cons: a secret that
Coffer neither injected nor recognises — a home-grown token in an argument, a
password in free text — is stored in plaintext for the retention period; the
log becomes a store of file contents and query results the agent saw, readable
by anyone who can read `runs.db` or call `coffer log`; 16 KB hides the tail of
a large result. It wins because the gap it closes (not knowing what a call did)
is felt on every failure, while the residual risk is bounded by the masking,
the retention period and the switch.

### Option B — Keep recording metadata only (the previous design)

Pros: nothing the call carried can ever leak from the log; no masking code to
get wrong. Cons: the log cannot answer what a call did, which is what people
open it for; debugging a custom tool means re-running it by hand with the same
arguments, and an agent's past call usually cannot be re-run faithfully. It
loses because the record stopped being useful for its main question.

### Option C — Mask every secret in the vault, not only those the call carried

Decrypt every stored secret and replace any occurrence in the content.

Pros: catches a vault secret an agent passed by hand, which Option A only
catches if the rules recognise its shape. Cons: every call would decrypt every
secret, outside the per-destination approval each one is released under; a
secret approved only for one server would sit in memory while recording a call
to another. It also costs a scan per secret per call. It loses on the approval
boundary: masking must not become a path that decrypts more than the call
itself was allowed to.

### Option D — Record content only when a call fails

Pros: keeps successful calls, the bulk of traffic, payload-free; failures are
where content helps most. Cons: a call that "succeeded" with the wrong result is
as common a question as a failure, and in-band tool errors are already
ambiguous; the masking risk on a failed call is the same as on a successful
one. It loses because it halves the value without halving the risk.

### Option E — Off by default, opt in

Pros: nothing new is stored until someone asks. Cons: the record is needed
after the fact; switching it on once a call has gone wrong is too late for that
call. The person chose on by default when the plan was agreed (2026-10-09). It
loses on that choice; the switch stays one click away.

### Option F — A larger cut, or none

Pros: a whole result is kept. Cons: a single file read or search can be
megabytes, and at agent call rates the log would grow by gigabytes a month.
16 KB keeps a typical JSON result whole and the head of a large one. It loses
on size.

## Decision

Every routed call stores its arguments and its result or error, and a custom
HTTP tool's call also stores its request and response. Before the row is
written, the secret values the gateway injected for that call, credential
headers, secret-named fields and anything the bundled plaintext rules recognise
are masked as `••••••`, and each part is cut at 16 KB with its original size.
Masking never decrypts a secret the call was not already carrying. Recording is
on by default and switched per machine; calls recorded while it was off keep
metadata only. Call content never goes to `daemon.log`, `error_message` stays a
Coffer-authored summary, and the model proxy still stores no prompt or
completion.

## Consequences

- A new path that injects a secret into an upstream must register the value
  with the supervisor's per-server overlay (`mask_values`), or its echo is
  masked only if the rules recognise it.
- A custom tool's request and response are recorded through the exchange sink
  in `application/mcp/call_content.py`; the HTTP client masks its own
  credentials before publishing them.
- Masking rules live in `domain/activity_content.py`; the backstop scan in
  `infrastructure/mcp/invocation_scrub.py`. Both run before insert, so a stored
  row is never rewritten.
- The Activity call drawer and `coffer log call <id>` read one call with its
  content; lists stay light because they defer the column.
- Turning recording off does not erase content already stored; it ages out on
  the invocation log's retention period.
