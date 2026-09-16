<!--
PR title must follow Conventional Commits (same shape as commit subject):
  <type>(<scope>): <subject>
Limits come from .commitlintrc.yaml, which the pr-title workflow and the local
commit-msg hook both read: subject ≤ 120 chars, whole header ≤ 150. Case is not
enforced. See .agents/workflow.md "Commits" for the full rule set.
-->

## What

<!-- One paragraph: what changed. -->

## Why

<!-- The motivation. Link issues, specs, or earlier conversation. -->

## How to test

<!--
- If the change has spec acceptance scenarios, list which scenarios are now
  covered (e.g., "mcp-gateway acceptance scenario `register and list`").
- Otherwise describe how a reviewer can manually exercise the change.
-->

## Spec references

<!-- Spec ids — the folder path under specs/, named and never numbered
     (e.g. `mcp-gateway`, or `channels/telegram` for a child spec) — or N/A. -->

## Screenshots

<!-- Required for UI changes. Delete this section otherwise. -->

## Breaking changes

<!-- Call out any breaking change explicitly. Delete if none. -->

---

- [ ] `make verify-all` is green locally
- [ ] PR title matches the squashed commit subject (Conventional Commits, within .commitlintrc.yaml's caps)
- [ ] AI-authored commits carry `Co-authored-by: <Agent> <noreply@...>`
- [ ] Constitution / .agents/ docs updated if conventions changed
