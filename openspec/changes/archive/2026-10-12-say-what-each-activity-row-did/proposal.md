## Why

The Activity page's rows still do not say what happened. 37 of the 87 audit
events read as a fixed sentence with no object ("Stored a secret", "Ran a
converge round"), although every one of them records the fields that would
name it. Worse, `secret_resolved` always reads "Handed a secret to a coffer run
command", so each time Coffer itself hands a secret to a server, custom tool or
connection it starts, the page claims a `coffer run` happened, with the actor
shown as the raw word `coffer`. These hand-offs are frequent and bury the real
changes.

## What Changes

- Every audit sentence names its object, and a secret use where the value went
  (the secret, the destination and the variable or header, or the program and
  folder), from fields already recorded; old rows read the same way.
- `secret_resolved` reads by what happened: Coffer's own hand-off or a
  `coffer run`.
- Who reads in words; `coffer` is Coffer.
- Secret uses (`secret_resolved`, `secret_revealed`) get their own Activity
  tab, **Secret use**, with a key icon; the Changes tab holds only changes;
  repeated uses of one secret by one destination within ten minutes fold into
  one row with "×N".
- `GET /api/v1/audit` takes `nature=change|use`; `coffer log audit --nature`.

## Capabilities

### Modified Capabilities

- `web-ui`: Activity gains the Secret use tab, sentences that name their
  object, actor words.
- `resource-framework`: the audit log tells a secret's use from a change.

## Impact

- Backend: audit route, service and repository filter; `AuditEventType` use set.
- Frontend: Activity tabs, sources, sentences, actor labels, folding; en/zh.
- CLI: `coffer log audit --nature`.
- Docs: Activity guide, observability (en + zh); ADR for the separate tab.
- Canvases: System (Activity).
