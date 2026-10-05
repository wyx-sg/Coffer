# Every Web UI and Desktop Operation Has a `coffer` Command Over the Same Route

**Status**: Accepted
**Date**: 2026-10-05
**Deciders**: Yuxing Wu
**Related**: [The Resource Framework Is Core Domain, Designed Before the Second Kind](resource-framework-upfront.md), [The Wire Contract Is Generated From the Pydantic Models, and the Frontend Client From the Contract](wire-contract-generated-from-the-pydantic-models.md), [Only a Present Human Sees a Secret or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md), [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md), spec resource-framework "Offer every management operation on the command line", spec mcp-gateway "Manage custom tools from the command line", spec secret "Approve from the command line with the person's own presence check", OpenSpec change align-cli-with-ui-and-add-tool-environments

## Context

Coffer is managed by people on its web pages and by agents working beside
them. Until this decision the rule was that the command line carries only what
needs it: a command existed only when a program runs it, it must work while the
daemon is down, a hand-off prompt names it, or the web UI cannot do the job.
Every other operation was REST plus a page, and the trimmed command line had
about twenty leaves.

That rule assumed the person at the page is the one managing Coffer. In
practice an agent is asked to "add the staging environment to the payments
tools", "turn that MCP server off for Codex" or "approve the GitHub token for
the new URL", and the only way it could do so was to drive the web UI, to
call the management API by hand with the per-start token, or to edit vault
files — the first is fragile, the second reimplements the CLI badly in every
prompt, and the third skips validation, audit and the lifecycle hooks. Custom
tools had no command at all, so an agent that had just written an OpenAPI
document could not import it.

## Options Considered

### Option A — A command for every UI operation, over the page's own route (chosen)

Every management operation a person can do on a page or in the desktop app has
a `coffer` command that calls the same REST route the page calls. The commands
are declared, not hand-written: one `RouteCommand` record names the command
words, method, route, the UI operation it stands for, its path names and query
options, and whether it takes a body; a builder turns it into a Typer command
with the shared contract (`--json`, `--data '<json>' | @file | -`, `--set`,
stable exit codes, the daemon's error codes unchanged). Every record lands in
one registry, and `scripts/cli_coverage.py` compares the registry with every
route the frontend's typed client calls and every IPC command the desktop shell
exposes, failing `make lint` on a gap and rendering the coverage table into the
CLI reference.

Pros: an agent does what a person does, with the same validation, audit and
lifecycle, and no new server code; a new page without a command fails the build;
the coverage table is the proof. Cons: a much larger command tree to keep
documented (generated) and tested (each declared command is run against a
recording transport).

### Option B — Keep the command line to what needs it (the previous rule)

Pros: a small surface. Cons: it fails the case above — an agent cannot manage
Coffer without scraping the UI or calling REST by hand — and it bred
exceptions argued one at a time.

### Option C — Expose the management API as MCP tools instead

Pros: an agent already speaks MCP. Cons: it puts every management mutation in
the tool list of every session (the gateway's tool budget and the reach model
both assume tools are the user's integrations, not Coffer's control plane), it
needs a second surface with its own auth story, and humans still have no
scriptable path.

### Option D — A local HTTP adapter or proxy that agents curl

Pros: no CLI work. Cons: a second network surface with its own token handling,
and no help, no stable exit codes and no presence hand-off.

## Decision

Every management operation a person can do on a web UI page or in the desktop
app has a `coffer` command calling the same route. Exempt are only plain file
contents a spec declares directly editable (knowledge documents, memory notes,
a skill's files, agents' own config and native-memory files) and acts that are
the window itself; registering, binding, reach, delivery and history restore
stay commands even where what they manage is a file. Internal YAML, `runs.db`
and secret ciphertext are never a reason to skip a command: no command and no
agent edits them as files.

A step that needs a person — approving a secret binding, revealing a value,
writing the master-key backup — is handed to the desktop app over a small
in-memory request queue in the daemon. The app runs its own Touch ID or
password check and signs a one-time grant pinned to the operation and to the
approval's target fingerprint; the command reads the result. No flag skips the
check, a cancelled or failed check leaves the approval pending, and no value,
signature or key reaches the command's output.

A spec that adds a UI operation ships its command in the same change; the rule
is stated in `.agents/openspec.md` and tested by the resource-framework
requirement named above.

## Consequences

- Easier: an agent manages Coffer through `coffer`, and its exit codes and JSON
  errors are stable enough to branch on; humans can script any page.
- Harder: every new route the frontend calls needs a registry row or an
  exemption, or `make lint` fails; the generated CLI reference grows.
- The CLI never reimplements a route: a command is a record over the typed
  route, so the daemon stays the only place behaviour lives.
- The presence gate is unchanged in strength: the CLI asks, the desktop app
  checks the person, and the daemon verifies the grant against the target it
  holds now, so a target that changed after the prompt approves nothing.
