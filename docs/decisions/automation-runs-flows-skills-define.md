# Automation Runs Flows Skills Define

**Status**: Proposed
**Date**: 2026-11-05
**Deciders**: Yuxing (owner)
**Related**: [Scheduled Tasks Are Turns Coffer Starts in a Chat](scheduled-tasks-are-turns-coffer-starts-in-a-chat.md), change `add-workflow-automation`

## Context

Scheduled tasks start a turn in a paired chat. Recurring work the owner runs —
following their developer tickets to delivery, a weekly report — needs a
check before any model starts, one owner per work item, a record of writes
whose result is unknown, working hours checked on every step, a hand-over
between agents and results kept locally. A Codex-only prototype proved the
mechanisms; none of them carry to another agent. The principles say Coffer
starts no agent runs, which the scheduled-tasks branch already contradicts.

## Options Considered

- **A — Coffer runs a flow a skill declares (chosen).** The task binds a skill's
  `automation.yaml`; Coffer owns trigger, policy, sessions, leases, the action
  ledger and run records; the skill owns steps and decisions; the workflow
  project owns business checkpoints.
- **B — Keep it in each agent's native automations.** No Coffer change, but
  every flow is rebuilt per agent and nothing enforces one owner or refuses a
  blind retry across agents.
- **C — A workflow DSL or visual orchestrator in Coffer.** Coffer would have to
  understand flows; two real flows fit stages + precheck + result schema.

## Decision

Option A. Details in the change's `design.md`. The principle "Not a second
agent" is amended so Coffer defines no flow but runs a skill's declared flow
on a trigger, under each agent's own permissions, never approving a tool call.

## Consequences

- One runtime for every agent Coffer drives; flows are added as skills.
- Coffer gains runtime-safety state in `runs.db` (leases, actions, model
  calls); business checkpoints stay in the workflow project.
- Automation turns stop using full permissions.
- The generic scheduled-task requirements move from `channels` to a new
  `automation` spec.
