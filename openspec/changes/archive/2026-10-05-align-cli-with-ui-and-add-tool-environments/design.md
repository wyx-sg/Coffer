## Context

The owner's decision (2026-10-05) replaces the minimal-CLI policy with parity:
whatever a person manages in the web UI or the desktop app, an agent can manage
with `coffer`. The same change adds environments to custom-tool groups, full
argument validation, and approvals that an agent starts and the person confirms
with Touch ID. This document records how.

## Decisions

### D1 — One route-backed registry is the command line's map

Every management command is a row in `surfaces/cli/registry/` naming its
command path, the REST route (method and path) it calls, the UI operation it
stands for (page and action, as the coverage table prints it) and its
acceptance scenario. Most rows are **declarative**: path parameters become
positional arguments, query parameters become options, and a body comes from
`--data`/`--set`; a generic runner builds the request, prints the answer and
maps errors to exit codes. Commands with a richer shape (custom tools,
approvals, secrets, the daemon lifecycle) are hand-written Typer commands that
register their rows in the same registry. Nothing reimplements a route: the
daemon's validation, audit and lifecycle are the CLI's.

Why not generate commands from the OpenAPI contract at run time: the command
names are a reviewed vocabulary (`coffer custom-tool env add`, not
`coffer post-custom-tools-name-environments`), and a generated tree would grow
a command for every internal route nobody should call.

### D2 — The coverage test reads the web UI's own calls

`scripts/cli_coverage.py` extracts every `(method, path)` the frontend calls
through its typed client and every `#[tauri::command]` the desktop shell
exposes, and the policy test asserts each is covered by a registry row or by an
exemption with a category (`file-content`, `window`, `internal`) and a one-line
why. The same data renders `docs-site/reference/cli-coverage.md` (and its `zh/`
twin): UI operation → route → command → acceptance. A route the web UI starts
calling without a command fails `make verify`; that is the parity guarantee.

`internal` covers the plumbing a page needs to run but a person never chooses
(the event stream, the handshake, the menu-bar count). `window` covers acts
whose whole meaning is the window: a native folder picker, opening a file in
the editor, terminal or Finder, the interface language and theme.

### D3 — CLI contract

- `--json` on every command: the daemon's answer verbatim on stdout; on error
  `{"error": {"code", "message", "details"}, "exit_code"}` on stderr.
- `--data '<json>' | @path | -`, plus repeatable `--set a.b=value` (the value
  parsed as JSON when it parses, else a string) merged over `--data`.
- Never prompts when stdin is not a terminal; `secret set` still reads stdin.
- Exit codes extend the existing table: 11 presence not confirmed (cancelled,
  failed, timed out), 12 desktop app unavailable, 13 a `--wait` ran out.
- Stable error codes are the daemon's (`error.code`); the CLI adds
  `CLI_INVALID_INPUT`, `CLI_APP_UNAVAILABLE`, `CLI_PRESENCE_NOT_CONFIRMED` and
  `CLI_WAIT_TIMEOUT` for what it decides itself.
- A change that leaves approvals pending prints them with
  `next: coffer approval approve <id>…` and exits 9 (unchanged meaning:
  "saved, waiting for a person").

### D4 — Environments live in the group, normalised on read

```
HttpApiTransport
  environments: [HttpApiEnvironment]    # ≥ 1, names unique
  timeout_seconds                        # the group's default
  tools, source
  secret_refs                            # derived: {"<key>:<header>" | "<header>": ref}
HttpApiEnvironment
  name, key, description, enabled
  base_url, headers, secret_refs, auth_schemes, variables, timeout_seconds?
```

A stored group from before environments (`base_url`, `headers`, `secret_refs`,
`auth_schemes` at the top) is lifted on validation into one environment named
`default` with `key = ""`. `key` is the environment's **binding key**: fixed
when the environment is created (its first name), kept across renames, and
`""` only for the lifted environment. The derived top-level `secret_refs` keeps
every kind-agnostic walker (the missing-secret probe, the citation index, the
attention sources, delete-time release) working without knowing about
environments, because each slot name is unique across environments.

Variables are non-sensitive text (a value that looks like a credential is
refused, as for plain headers) substituted for `{env:NAME}` in a tool's path,
query, headers and body — never in the base URL, so the host a secret goes to
is the environment's base URL alone. A tool that names a variable some enabled
environment lacks is refused when saved.

### D5 — Selecting an environment per call

The gateway adds a reserved argument `coffer_environment` to every custom
tool's advertised schema — an `enum` of the group's enabled environments,
`required` once there is more than one — and removes it from the arguments
before validation and rendering, so it never reaches the path, query or body.
A tool's own schema may not declare it. The connection keeps no "current"
environment: each call resolves its own environment and its own secrets, so
concurrent calls to the same tool on different environments cannot mix URLs,
headers, variables or credentials. A group with one enabled environment uses
it when the argument is absent — a single target is not shared state.

### D6 — Each environment is its own secret destination

`mcp_destinations()` returns one destination per enabled environment: the
same `kind` and `uid` (the group), the label `<group> · <environment>`, the
target `http_api <base_url>` and slots `<key>:<header>` (`<header>` for the
lifted environment). Keeping the destination uid the group's means every
existing per-resource view of approvals still finds them; keying slots by the
environment's binding key isolates bindings: approving `live` approves nothing
for `test`, and moving `test`'s URL supersedes only `test`'s approvals. The
lifted environment keeps the exact slot and target it had, so its approvals
survive the upgrade. The kind's destination callback may now return a list; the
wiring accepts a single tuple too.

At call time the connection resolves the chosen environment's refs through the
guarded resolver for that environment's destination — nothing is resolved at
spawn — so a pending or missing secret is an in-band tool error naming the
approval ids and `coffer approval approve <id>`, and only for that environment.

### D7 — A JSON Schema validator in the domain

`domain/mcp/json_schema.py` is a small, pure validator (standard library only,
as the domain fence requires) for the vocabulary OpenAPI imports and hand-
written tools use: `type` (incl. lists and OpenAPI 3.0 `nullable`), `enum`,
`const`, `minimum`/`maximum`/`exclusive*`/`multipleOf`, `minLength`/
`maxLength`/`pattern`, `items`/`prefixItems`/`minItems`/`maxItems`/
`uniqueItems`/`contains`, `properties`/`required`/`additionalProperties`/
`patternProperties`/`minProperties`/`maxProperties`/`propertyNames`,
`allOf`/`anyOf`/`oneOf`/`not`, `if`/`then`/`else`, `dependentRequired` and
local `$ref` (`#/...`, with `$defs`/`definitions`). It has two entry points:
`check_schema()` (the schema is well formed: keyword types, valid regexes,
resolvable refs, no `$ref` cycle without progress) at save time, and
`validate()` returning every error as `{path, keyword, message}` at call time.
The render step is reached only with valid arguments.

### D8 — Desktop requests broker the CLI to the shell

The daemon keeps a short in-memory queue of **desktop requests**
(`/api/v1/desktop/requests`): `{id, op, approval_ids | ref, status, message,
created_at, expires_at}` with ops `approve`, `reveal`, `export_master_key`,
`update_check`, `update_install`. `coffer approval approve` creates one and
waits. The shell polls the queue every second (each poll is its heartbeat),
claims a request, and runs the *same* code path the page's buttons run: it
reads every approval from the daemon, keeps those still pending, shows the
operating system's prompt naming each action, target, secret and environment,
asks for a challenge, signs, and calls the approve route. The daemon marks the
request done when the approve route redeems a grant for its ids; the shell
reports cancel or failure. The CLI reports the approvals' real status as the
daemon holds it — a forged "approved" report changes nothing.

When no shell has polled for five seconds, the CLI starts the app
(`open -b <bundle id>` on macOS) and waits up to 30 seconds for a heartbeat; if
none comes (no app, not macOS, a headless session) it exits 12 and the approval
stays pending. Nothing clicks the UI, and the request carries no secret: the
agent learns approved/cancelled/failed, never a signature, nonce or key.

Reveal and key backup started from the CLI run the shell's existing flows;
the value is shown in the app window and the passphrase is typed there, never
returned to the command.

### D9 — A single approval's grant is pinned to its target

The single-approval grant was signed over the approval id; the target it named
could move between the prompt and the approve request. The shell now reads the
approval's `target_fingerprint` before the prompt and signs `approve` over
`<id>@<fingerprint>`, sending the fingerprint with the request; the daemon
re-evaluates destinations, then applies the approval only if it is still
pending for that fingerprint. A batch already signs `(id, fingerprint)` pairs.
The old id-only grant stays accepted for a page that predates the shell.

### D10 — Environment in the invocation log

Migration `0151` adds `mcp_invocations.environment` (nullable text). The
gateway records the environment a custom-tool call resolved; the MCP server
page and `coffer log mcp` show it. No argument, header or credential is logged.

## Risks / Trade-offs

- **The command tree grows large.** Mitigated by one registry, generated help
  and a coverage document; the alternative — agents driving REST by hand —
  bypasses no less validation but has no help, no exit codes and no review.
- **Mixed versions over sync.** A machine on an older Coffer reads a group with
  `environments` and no top-level `base_url` as invalid. Vault sync already
  expects machines to run one version; the lifted form is written only once a
  group is saved.
- **An agent can raise presence prompts.** Each prompt says exactly what it
  approves and the person can cancel; one request is shown at a time and
  requests expire after two minutes.
