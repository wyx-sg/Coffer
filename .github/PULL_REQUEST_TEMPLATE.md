<!--
PR title must follow Conventional Commits (same shape as commit subject):
  <type>(<scope>): <subject>     ≤ 72 chars, lowercase, no trailing period.
See agents/workflow.md "Commits" for the full rule set.
-->

## What

<!-- One paragraph: what changed. -->

## Why

<!-- The motivation. Link issues, specs, or earlier conversation. -->

## How to test

<!--
- If the change has spec acceptance scenarios, list which scenarios are now
  covered (e.g., "001-mcp-servers acceptance scenario `register and list`").
- Otherwise describe how a reviewer can manually exercise the change.
-->

## Spec references

<!-- Spec IDs (e.g., 001-mcp-servers) or N/A for pre-spec scaffolding. -->

## Screenshots

<!-- Required for UI changes. Delete this section otherwise. -->

## Breaking changes

<!-- Call out any breaking change explicitly. Delete if none. -->

---

- [ ] `make verify-all` is green locally
- [ ] PR title matches the squashed commit subject (≤ 72 chars, Conventional Commits)
- [ ] AI-authored commits carry `Co-authored-by: <Agent> <noreply@...>`
- [ ] Constitution / agents/ docs updated if conventions changed
