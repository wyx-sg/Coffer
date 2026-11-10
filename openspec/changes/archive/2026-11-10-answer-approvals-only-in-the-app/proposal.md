## Why

On 2026-10-29 an agent requested `coffer run` access to two secrets, never told
the owner, and three minutes later refused its own request with `coffer approval
reject`. The refusal stood, so every later agent was told the owner had refused
it. Approving and refusing are the owner's decisions; the command line should
not answer approvals at all. Separately, an agent refused a custom tool because
its response carries a login token, waiting for a response filter Coffer does
not have.

## What Changes

- Remove the `coffer approval` command group (`list`, `show`, `approve`,
  `reject`, `ask-again`). Approvals are answered only on the app's Secrets page.
- A waiting approval is reported (exit 9, custom tool in-band error,
  `SECRET_BINDING_PENDING`) with its ids and "ask the developer to answer it in
  the Coffer app"; a standing refusal says the developer presses Ask again in
  the app.
- The desktop request queue no longer carries approvals; the shell's command
  line approve flow is removed.
- coffer-guide: call a tool whatever its response holds; report a waiting
  approval and leave it for the developer.
- Spec secret: "Approve from the command line with the person's own presence
  check" becomes "Answer a secret's approval only in the app"; desktop-app
  "Serve the command line's desktop requests" drops approval requests. Edited in
  place (scenarios removed and renamed), hence `skip_specs`.
- ADRs only-the-person-answers-a-secret-approval-in-the-app and
  a-tool-response-reaches-the-agent-as-the-upstream-sent-it.
