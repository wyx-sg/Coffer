# A Kind Plugs In as One Frozen Record of Optional Hooks: Validators Before the Write, Reactions After

**Status**: Accepted
**Date**: 2026-09-18
**Deciders**: Yuxing Wu
**Related**: [The Resource Framework Is Core Domain](resource-framework-upfront.md), [Composition Root With Explicit Wiring](composition-root-explicit-wiring.md), [Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md), [Per-Agent Resource Scope](per-agent-resource-scope.md), [Sync Withholds Derived Output](sync-withholds-derived-output.md), spec resource-framework "Keep creation a per-kind seam", spec resource-framework "Run the kind's cleanup before a deletion completes", spec resource-framework "Let a kind refuse a deletion before anything is torn down", spec resource-framework "Treat a resource's name as a mutable label", PR #386, PR #406

## Context

[The Resource Framework Is Core Domain](resource-framework-upfront.md) puts the
lifecycle of every resource — register, update config, enable/disable, scope,
rename, delete — in one kind-agnostic `ResourceService`, and forbids that
service from importing any kind. But almost every kind has something to say
about some of those operations:

- A skill's row must be backed by a master folder, so the generic create path
  must not make one; a builtin skill must not be deletable; disabling a skill
  must reclaim its delivered copies; renaming it must move its directory.
- A channel's `default_agent` must name a registered agent inside the channel's
  own scope, whichever of config or scope is being edited.
- An MCP server's name is its tools' namespace prefix, so `__` is reserved; its
  config carries secrets that must not reach the audit log; deleting or renaming
  it must release live upstream connections.
- A provider starts scoped to the agents its protocol can serve, not to every
  agent.
- Memory rows are derived per machine and must not sync; one skill
  (`coffer-guide`) is derived output and must not sync either.

The core needs a way to consult a kind at the right moment of each operation
without knowing which kinds exist, and the contract has to make one property
impossible to get wrong: a kind that objects to a change must object **before**
the change is persisted and audited, because afterwards there is nothing
honest left to do with the objection.

## Options Considered

### Option A — One frozen `Kind` record of data plus optional hook callables (chosen)

`Kind` in `domain/resource.py` is a `@dataclass(frozen=True)`. Each kind's
`make_<kind>_kind()` factory (`application/<kind>/kind.py`) returns one,
closing over whatever services its hooks need; the composition root puts it in
the kinds dict `ResourceService` looks up. Every hook is optional (`None` means
"nothing to say"), may be sync or async (the service awaits an awaitable), and
is handed the `Resource` it concerns rather than an identifier to look it up
by. Hooks fall into declared groups, and the group decides when the service
calls it:

**Descriptor and flags**

| Field | Meaning | Set by |
| --- | --- | --- |
| `name`, `display_name`, `config_schema` | Kind key, label, Pydantic model every config is validated against on write | every kind |
| `generic_create_allowed` | `False` refuses creation (and config update) through the generic `POST`/`PATCH`; the kind's own service passes `allow_lifecycle_kind=True` | `False` for `agent`, `skill`, `knowledge`, `memory` |
| `supports_scope` | Whether a non-null per-agent scope may be set | `True` for `mcp_server`, `skill`, `channel`, `provider` |
| `converges` | Whether the kind's rows travel to the sync remote | `False` for `memory` |
| `converges_row(config)` | Per-row refinement of `converges`; can only withhold | `skill` (withholds `coffer-guide`) |

**Pure functions of the config** — consulted while building a write, never
reject it:

| Hook | Used for | Set by |
| --- | --- | --- |
| `credential_ref_extractor(config)` | The refs the service probes in the credential store before any write | `mcp_server`, `channel`, `provider` |
| `audit_redactor(config)` | An audit-safe copy of the config | `mcp_server` |
| `default_scope(config)` | The scope a new row starts with, consulted once at register | `provider` |

**Pre-write validators** — run before persistence; raising rejects the
operation with nothing changed:

| Hook | Operation | Set by |
| --- | --- | --- |
| `validate_name(name)` | register and rename | `mcp_server` (reserves `__`), `skill` (frontmatter name rule) |
| `validate_config(config)` | register only, so an unrelated edit never re-probes the filesystem | `channel`, `provider` |
| `on_update_config(resource, config)` | update config | `channel`, `provider` |
| `on_rename(resource, new_name)` | rename — moves whatever is keyed by the name; a failure aborts, and on a lost race the service calls it again to move back | `skill`, `knowledge`, `memory`, `mcp_server` |
| `validate_scope_for(resource, scope)` | update scope | `channel` |
| `validate_delete(resource)` | delete, before any cleanup | `skill` (refuses builtin skills with `RESOURCE_PROTECTED`) |

**Post-write reactions** — run after persistence and audit; they catch up with
a change that already happened and have no way to undo it:

| Hook | Operation | Set by |
| --- | --- | --- |
| `on_enabled_changed(resource)` | enable/disable, only on a real transition | `agent`, `skill`, `knowledge` |
| `on_scope_changed(resource)` | update scope | `skill` |
| `on_delete(resource)` | delete — the one reaction that runs *before* the row is removed, so cleanup can still read it, but after `validate_delete` has let the delete through | `agent`, `skill`, `knowledge`, `memory`, `mcp_server`, `channel` |

- **Pros.** The asymmetry between validators and reactions is structural: the
  service calls one group before `repo.*` and the other after `audit.record`,
  so a kind cannot put a refusal where it would arrive after the write. A kind
  declares only what it needs and leaves the rest `None`.
  Because the record is data, the core stays importable without any kind and
  is tested against a `fake_kind`. Closures let a hook reach its kind's
  services without the core knowing their types.
- **Cons.** The record grows a field whenever some kind needs a new moment
  (rename, per-row sync withholding and scope pre-validation were each added
  this way), and a field's contract lives in its comment. Hook names are not
  perfectly regular (`on_update_config` and `on_rename` are validators despite
  the `on_` prefix).
- **Why it wins.** It is the smallest shape that keeps the core ignorant of
  kinds and makes the pre-write/post-write distinction impossible to blur.

### Option B — An abstract `Kind` base class; each kind subclasses and overrides methods

- **Pros.** Familiar; an IDE lists the overridable methods; default
  implementations can share behaviour.
- **Cons.** Base-class defaults invite logic to accumulate in the core's
  hierarchy (a "god base class"), and subclasses tend to call `super()` in
  different places, which is exactly how validation and reaction ordering gets
  blurred. A subclass needs its services injected through a constructor, so
  the class lives in `application/` while the core in `domain/` has to import
  the base from somewhere both can see — the same record, with inheritance on
  top. Whether a kind "has" a hook becomes "did it override the method", which
  the service cannot see without introspection, so every hook is always called.
- **Why it loses.** It adds inheritance without adding anything the record
  lacks, and loses the explicit "this kind supplies nothing here".

### Option C — Per-kind services called by name from the core

`ResourceService` (or each route) branches on `kind` and calls the right
service: `if kind == "skill": await skill_service.on_delete(...)`.

- **Pros.** The call path is completely explicit; no indirection.
- **Cons.** The core imports every kind, which the import-linter contract
  "Kind-agnostic core does not import kind-specific code" forbids, and every new
  kind edits the core. Guards drift per route: before `validate_delete`, the
  builtin-skill refusal would have had to be repeated on the kind's own DELETE
  and on the generic one, and a second route would quietly miss it.
- **Why it loses.** It makes the framework know its kinds.

### Option D — Domain events on a bus: the core publishes, kinds subscribe

`ResourceService` emits `ResourceCreated`, `ResourceRenamed`, `ScopeChanged`, …;
each kind subscribes to what it cares about.

- **Pros.** Fully decoupled; any number of subscribers; natural for reactions.
- **Cons.** Events are after-the-fact by nature, so refusals do not fit:
  validation would need a second, synchronous "ask" channel with ordering and
  first-refusal-wins semantics — the hook record again, but implicit. Delivery
  order and failure handling across subscribers become policy the core must
  define, and whether a kind is consulted at all depends on a subscription
  made elsewhere, the same silent-miss failure mode as wiring through
  `app.state` ([Composition Root With Explicit Wiring](composition-root-explicit-wiring.md)).
- **Why it loses.** It serves reactions well and validators badly, and the
  validators are the half that must never be missed.

### Option E — A descriptor that also carries the kind's surfaces (routers, CLI groups)

A `KindModule`-style record holding `http_routers` and `cli_groups` beside the
hooks, so registering a kind also mounts it.

- **Pros.** One object per kind for everything.
- **Cons.** The record lives in `domain/` and would have to reference surface
  artefacts, typed `Any` to avoid importing FastAPI and Typer. Such a carrier
  existed and nothing used it; PR #386 deleted it.
- **Why it loses.** Surfaces are mounted by the composition root; the `Kind`
  describes lifecycle only.

## Decision

A kind plugs into the framework as one frozen `Kind` record in
`domain/resource.py`: a config schema, flags, and optional hooks, each hook
handed the `Resource` it concerns and allowed to be sync or async. The record
carries no surface. Hooks are divided by when the service calls them, and a
new hook must be declared in one of the groups:

- **Pre-write validators** may refuse; they run before anything is persisted,
  and a refusal leaves the resource exactly as it was. Refusing a delete is
  `validate_delete`'s job, never `on_delete`'s.
- **Post-write reactions** run after persistence and audit and must not be
  used to refuse — a reaction that raises cannot un-persist an audited change.
  `on_delete` runs before the row is removed only so its cleanup can still
  resolve it; if it raises, the exception propagates and the row stays, but
  whatever cleanup already ran is not rolled back, which is why refusal
  belongs in `validate_delete`.
- **Pure config functions** (`credential_ref_extractor`, `audit_redactor`,
  `default_scope`, `converges_row`) take the config alone, so any caller can
  ask them with what it already holds — including the sync applier, which holds
  a document with no row behind it yet.
- **Creation is the one operation a kind may keep.** A kind with an invariant
  beyond config validation sets `generic_create_allowed=False` and creates
  through its own service; there is no generic `coffer resource create` for
  it. Everything after creation — enable, scope, rename, delete — is generic
  (config update stays with the owning service too, for the same reason).

## Consequences

- Each operation's order is fixed in one place: `ResourceService` in
  `application/resource_service.py`, with scope and rename in
  `resource_scope_ops.py` and `resource_rename_ops.py`. For example, delete is
  `validate_delete` → `on_delete` → row removed → orphaned credentials released
  → audited; rename is name rules → collision check → `on_rename` → column
  write (with `on_rename` called again to move back if a racing writer took the
  name) → audited.
- A guard declared on the `Kind` holds on every surface at once — the kind's own
  route, the generic route and the CLI — rather than one guard per route.
- Adding a hook is a change to `domain/resource.py` and to the service method
  that calls it, reviewed as a contract change; the comment on each field is
  its specification.
- Which kinds may carry a scope and where each enforces it is decided in
  [Per-Agent Resource Scope](per-agent-resource-scope.md); why `converges` and
  `converges_row` exist is [Sync Withholds Derived Output](sync-withholds-derived-output.md).
