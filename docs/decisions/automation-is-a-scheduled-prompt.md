# Automation Is a Scheduled Prompt; the Flow Belongs to the Skill

**Status**: Accepted
**Date**: 2026-11-06
**Deciders**: Yuxing (owner)
**Related**: [Scheduled Tasks Are Turns Coffer Starts in a Chat](scheduled-tasks-are-turns-coffer-starts-in-a-chat.md), [An Agent Notifies the Owner Through a Built-in Tool](an-agent-notifies-the-owner-through-a-built-in-tool.md), spec channels, research note [Scheduled agent tasks](../research/scheduled-agent-tasks.md)

## Context

Scheduled tasks start a turn in a paired chat. The owner's recurring work —
following their developer tickets to delivery, a weekly report — showed two
gaps:

- **Not every task has a chat.** A nightly check of a repository belongs in a
  directory, on an agent, not in a messaging app. Claude Code's and Codex's
  own automations run exactly that way.
- **A flow has steps.** The ticket flow checks for work before spending a
  model call, keeps one owner per ticket, avoids retrying a write whose result
  is unknown, respects working hours and may hand a stage to another agent.

A first design (2026-11-05) answered the second gap with a runtime in Coffer.
On review the owner judged that every task is different, that each of those
mechanisms is a step a skill can take for itself, and that the first version
should follow what Claude Code and Codex ship: a prompt on a schedule.

## How comparable products do it

From the research note, re-read 2026-11-06:

- **Codex automations.** An automation is a prompt, a schedule (an rrule),
  a model, the working directories and a notification policy. A standalone
  automation opens a new thread per run; a thread automation runs back in the
  conversation it came from. It can be created from a skill. No step model,
  no ledger: what the run does is the prompt's.
- **Claude Code Desktop scheduled tasks.** A task is a prompt, a schedule
  (cron, a one-off time or manual), a folder and a model. Every run is a new
  session in that folder; the history lists each run as running, succeeded or
  failed and opens its session. A missed slot runs once, late.
- **OpenClaw, Hermes Agent.** Cron jobs whose payload is a message to the
  agent, in a new session by default or a named one.

None of them declares steps, prechecks, work items or checkpoints. Where a
flow needs those, the prompt invokes a skill that does them.

## Options Considered

### A — A scheduled prompt; the chat is optional; the flow is the skill's (chosen)

A task is a schedule (with an optional IANA timezone), a prompt, and either a
chat or none. In a chat it runs as before, in that chat's conversation or a
fresh one, and answers there. With no chat it opens a new conversation of its
own on the task's agent, model and directory, and its answer stays in that
conversation; the run's history row opens it, and the agent can reach the
owner with `coffer__channel_notify`. Agent follow-ups and the daily report
stay bound to their chat: a follow-up returns to the thread that booked it.

- **Good:** the smallest change that covers both gaps; it is what the owner
  already knows from the two agents; a flow is written once, as a skill, and
  any agent Coffer drives runs it; nothing in Coffer has to understand a flow.
- **Costs:** safety a flow needs (one owner per item, no blind retry, working
  hours) is the skill's to get right, per skill; Coffer does not enforce it.
  A run keeps the same permissions as a turn the owner sends.

### B — A workflow runtime in Coffer (the 2026-11-05 draft)

A task binds a flow the skill declares (`automation.yaml` or frontmatter):
a precheck command, work items with leases, a ledger of writes whose result is
unknown, checkpoints, working hours and holidays checked on every step, a
different agent per stage, and an unattended permission mode.

- **Good:** those guarantees hold across agents without each skill
  re-implementing them; a precheck could skip a model call.
- **Lost because:** every recurring task is different, so the declaration
  either grows into a language or fits only the first flow; each mechanism is
  a step the skill can already take (run the check script, keep a lock or a
  state file, read the clock); no comparable product builds one; and it adds
  state (`runs.db` leases, actions) and a permission mode the owner did not
  want ("先不做任何权限管控").

### C — Leave recurring work to each agent's own automations

- **Good:** no Coffer change at all.
- **Lost because:** a task would be rebuilt per agent, could not run on the
  other agent, could not answer in a channel chat, and the owner's follow-ups
  and daily report, which already live in Coffer, would stay a separate
  system.

## Decision

Option A. Coffer starts a turn from a prompt on a schedule, in a chat or in a
fresh conversation of its own; it defines no flow and enforces no flow-level
safety. A flow is a skill, invoked from the prompt.

## Consequences

- A task's `chat` is optional. With none, the session is always fresh, the
  agent is required, and no one is mentioned; a run ends `done` or `failed`
  with its turn, and nothing is posted anywhere.
- Every schedule shape may name an IANA timezone; without one it is the
  computer's local time.
- The principle "Not a second agent" says Coffer runs a prompt on a schedule
  and leaves the steps to skills, rather than having no scheduler at all.
- Option B is reconsidered only for a mechanism that several real skills need
  and none can do for itself.
