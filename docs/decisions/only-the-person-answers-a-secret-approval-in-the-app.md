# Only the Person Answers a Secret's Approval, and Only in the App

**Status**: Accepted
**Date**: 2026-11-10
**Deciders**: Yuxing Wu
**Related**: [Agents May Configure Coffer; Only a Present Human Sees a Secret's Plaintext or Sends It Somewhere New](only-a-present-human-sees-a-secret-or-sends-it-somewhere-new.md) (rule 3 is narrowed here), spec secret "Answer a secret's approval only in the app", "Report a pending approval on the command line by exiting", spec desktop-app "Serve the command line's desktop requests"

## Context

A secret that would go somewhere new waits for a person's approval. Until
2026-11-10 the command line could answer one: `coffer approval list`, `show`,
`approve` (which asked the desktop app to run Touch ID), `reject` (no check:
refusing only narrows) and `ask-again`. Every message that reported a waiting
approval ended with `next: coffer approval approve <id>`.

On 2026-10-29 a Codex session answering a SeaTalk message ran `coffer run` with
two standalone secrets. The daemon recorded two local-program requests and the
desktop app raised a notification for each. The agent never told the owner; three
minutes later it ran `coffer approval reject` on both to tidy up. A refusal
stands for its target, so from then on every agent's `coffer run` with those
secrets answered "refused in the Coffer app", which the owner had never done.
On 2026-11-10 another agent, blocked by that refusal, asked the owner to "turn on
local program access" without knowing why it was off.

The owner's position: approving and refusing are the owner's decisions, so the
command line should not answer approvals at all.

How comparable tools split it (2026-11):

- **macOS privacy prompts (TCC)**: only the person's answer in the system prompt
  is remembered; an app cannot refuse on the person's behalf.
- **1Password CLI, `sudo` with Touch ID**: the biometric prompt unlocks an
  action the person is running themselves; nothing lets one program raise a
  prompt that approves another program's request.
- **GitHub environments**: a deployment waits for a required reviewer, who
  answers in the web UI; the run that asked can be cancelled, which is not a
  reviewer's rejection.
- **Docker Desktop, Claude Code permission prompts**: the prompt appears in the
  app the person is looking at; the requesting process only waits.

## Options Considered

### Option A — Remove `coffer approval`; answer only in the app (chosen)

No command lists, shows, approves, refuses or re-asks an approval. A command or
tool that meets a waiting approval names the ids and says the developer answers
it in the Coffer app; the desktop request queue no longer carries approvals.

- Pros: an agent can neither leave a refusal the person never made nor put an
  approve prompt in front of the person to be confirmed unread. One rule, no
  per-caller semantics. Less code: a command group, a desktop-request kind and
  the shell's half of it go away.
- Cons: a person working only in a terminal must open the app to answer. The
  REST routes stay for the page, so a determined local process with the API
  token can still call them; this closes the path agents are told to use, not
  every path (the same as before for approving, which needs a grant).

### Option B — Keep the commands; a refusal from the command line only withdraws

`coffer approval reject` would end the request without a standing refusal, so
the next use asks again; only the app's Reject would stand.

- Pros: an agent tidying up its own request no longer blocks later ones.
- Cons: the same verb means two things depending on who called it, and the
  caller is told by a header any process can set. `approve` still lets an agent
  raise a Touch ID prompt. The owner found the split arbitrary.

### Option C — Keep everything; tell agents in the guide not to refuse

- Pros: no code change.
- Cons: relies on every agent reading and following the guide; 2026-10-29 is
  what happens when one does not.

### Option D — Refusals never stand, from anywhere

- Pros: one rule, and no stale refusal can block anyone.
- Cons: an agent that retries keeps raising notifications for a request the
  person already refused; that is what the standing refusal is for.

## Decision

Option A. `coffer approval` is removed. Waiting approvals are reported with
their ids and "ask the developer to answer it in the Coffer app (Secrets page)",
on the command line (exit 9), in a custom tool's in-band error and in
`SECRET_BINDING_PENDING`; a standing refusal's message says the developer
presses Ask again in the app. The coffer-guide skill tells agents to report a
waiting approval and leave it, and, separately, to call a tool whatever its
response holds rather than refuse it for carrying a token. The desktop request
queue keeps reveal, key backup and import, update and uninstall.

## Consequences

- Rule 3 of the present-human ADR still holds (approving needs a presence
  grant); what changes is where the prompt can be started: only from the app.
- `scripts/check_removed_commands.py` fails any doc, spec or skill that still
  quotes `coffer approval`.
- Approvals made before this change are unaffected; a refusal an agent left
  earlier still stands until the person presses Ask again in the app.
