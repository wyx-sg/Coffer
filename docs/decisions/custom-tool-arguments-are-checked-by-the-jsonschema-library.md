# Custom Tool Arguments Are Checked by the `jsonschema` Library

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing Wu
**Related**: [What an Agent Fills in a Custom Tool Is an Input](what-an-agent-fills-in-a-custom-tool-is-an-input.md), spec mcp-gateway "Validate a custom tool's arguments before any request"

## Context

A custom tool's inputs are a JSON Schema. Coffer checks the schema when a tool
is saved and checks every call's arguments against it before any request is
sent, so a wrong call costs the API nothing and the agent gets one entry per
field to fix.

Until now this was a validator written by hand in the MCP domain package: 509
lines across two modules, standard library only, covering the draft 2020-12
validation keywords plus three older spellings (OpenAPI 3.0's `nullable`,
draft-04's boolean `exclusiveMinimum`, draft-07's array `items`). It was
written because the domain package was thought to be closed to third-party
libraries. The import-linter contract that guards the domain ("Domain is
pure") forbids other project layers and libraries that do I/O; it never
forbade pure computation, and the domain already uses Pydantic.

Coffer's direction since 2026-11-06 is to keep its own code as small as it can
(the owner: "coffer 的功能应该做得尽可能精简"). `jsonschema` 4.x is already
installed as a dependency of the `mcp` SDK, is the reference Python validator,
and covers every keyword the hand-written one did.

## Options Considered

### Option A — `jsonschema`, called from the domain package, behind the same two functions (chosen)

`domain/mcp/json_schema.py` keeps its two entry points, `check_schema` and
`validate`, and its `SchemaError(path, keyword, message)` shape, and does the
work with `Draft202012Validator`. A short normalising step rewrites the three
older spellings into draft 2020-12 first. The validator gets an empty
`referencing.Registry`, so it never fetches a remote `$ref`; `check_schema`
also refuses any `$ref` that is not local or points at nothing, as before. Errors on
`required`, `dependentRequired` and `additionalProperties` are split into one
entry per property, at the property's path, so the agent still sees one entry
per field.

- Pros: about 200 lines instead of 509; the library tracks the standard, so
  edge cases (`unevaluatedProperties`, `dependentSchemas`, the meta-schema's
  own checks) come for free; no new install, since `mcp` already brings it.
- Cons: messages are the library's own wording; two failures are reported a
  little differently: a `propertyNames` failure names the inner keyword
  (`pattern`), and extra items beyond a tuple are one `items` entry on the
  array, not one per item. Neither changes what is accepted or refused.
- Why it wins: the same refusals with less than half the code, and nothing new
  to install.

### Option B — keep the hand-written validator (the previous design)

- Pros: messages and paths fully under Coffer's control; no library coupling.
- Cons: 509 lines Coffer maintains for a solved problem; every keyword the
  standard adds is Coffer's work.
- Loses: the code it keeps buys nothing an agent needs.

### Option C — `jsonschema` in the infrastructure layer, behind a port

The plan first put the library in infrastructure, with the domain calling a
validator port.

- Pros: the domain imports no third-party code beyond Pydantic.
- Cons: the request rendering in the domain validates arguments itself, so
  every caller would need the port passed in; a port with one implementation
  that does no I/O is ceremony.
- Loses: the domain fence exists to keep I/O out, and this library does none.

### Option D — Pydantic's own schema support

- Cons: Pydantic generates JSON Schema from models; it does not validate an
  arbitrary instance against an arbitrary schema.
- Loses: it does not do the job.

## Decision

Custom tool schemas are draft 2020-12 and are checked by `jsonschema`'s
`Draft202012Validator`, from `domain/mcp/json_schema.py`. `nullable`, boolean
exclusive bounds and array `items` are rewritten before checking. No `$ref`
is ever fetched: the registry is empty and `check_schema` refuses a non-local
reference. `jsonschema` is a direct dependency in `backend/pyproject.toml`
because Coffer imports it.

## Consequences

- A library that does I/O still may not enter the domain; this one is allowed
  because it does none. A future change that needs remote `$ref` must not give
  the validator a retrieving registry; it resolves documents elsewhere first.
- The error wording agents see follows the library across upgrades; tests pin
  paths and keywords, not messages.
