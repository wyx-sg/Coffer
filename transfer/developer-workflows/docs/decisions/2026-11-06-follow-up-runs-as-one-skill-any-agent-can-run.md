# Developer follow-up runs as one skill any agent can run

Status: Accepted (2026-11-06, owner: "按你推荐你自己做，必须通用，所有agent都可以执行"; "coffer也可以执行")

## Context

The prototype (`coffer-delegating-work/scripts/follow_delivery*`, Codex
automations `developer` and `developer-2`, a `UserPromptSubmit` hook) worked
only under Codex: it launched `codex exec` children with fixed Luna/Sol
models, short-circuited a scheduled prompt with a Codex hook, and kept one
coarse `coordinate` action per event, so the individual writes a run made were
not recorded. An expired lease returned `reconcile` with no way to move on.

Coffer decided (thread "设计主动跟进和每日汇报", 2026-11-06) not to build a
workflow runtime. It offers a scheduled prompt (fresh session in a folder,
optional chat) and `coffer__channel_notify`. Everything else belongs to the
skill, and the skill must run the same under Claude Code, Codex, or an agent
Coffer starts.

## Decision

A separate skill `coffer-following-delivery` with one standard-library Python
CLI. The agent that the schedule starts is the executor; the CLI only answers
and records:

- `tick` — the cheap first call: working window + verified holidays (fail
  closed), source reads, change detection, due checks, one daily review, and
  unconfirmed writes. `idle` ends the run.
- Ticket locks (30 min, renewed by every recorded step). An expired lock
  passes to another run only when its holder left no unconfirmed write.
- A write ledger: `begin` before every external write (re-checks window,
  write switch, lock and open writes; same write twice → `already_done`),
  `end` after a readback with evidence. `unknown` blocks the ticket until
  reconciled; reconciling another run's write needs an outcome and evidence.
- A per-ticket checkpoint (stage / next / next check / note) that is the
  hand-over note for the next run or another agent.

Removed: the Luna classifier, the `codex exec` launcher and its isolation
flags, the hook entry, model names and scheduler ids in config. Two Codex
automations become one scheduled prompt.

## Alternatives

| Option | For | Against |
| --- | --- | --- |
| **Skill + CLI, scheduled agent executes (chosen)** | Works in any agent and in Coffer; one place for the rules; no model launcher to keep in sync with each agent's flags | Every run starts an agent even when idle (the tick keeps that to one command and one line) |
| Keep the prototype's two-tier Luna → Sol launcher | Cheap model for the "anything changed?" step | Codex-only flags, hook and model names; two extra processes to supervise; the scheduled agent is already a model |
| A runtime in Coffer (flow declaration, precheck, ledger, policy) | Idle runs could skip the agent | Rejected by the owner 2026-11-06: every task is different; Coffer stays lean |
| Durable-execution engine (Temporal, Step Functions) | Mature retries and history | A server for seven tickets; the steps are agent judgement, not code |
| Leave it inside `coffer-delegating-work` | No new skill | One skill would own two jobs: delegating one task and following tickets over time |

How comparable systems do it, and what was taken: Stripe/AWS idempotency keys
(a stable key per write; a repeat returns the earlier result), write-ahead
logging / outbox (record before acting, confirm after), Kubernetes controllers
and Renovate (each run re-reads remote state; store only what the remote cannot
tell you), Kubernetes/etcd leases (expiry plus a rule for safe takeover),
Temporal/LangGraph checkpoints (resume from the last recorded step).

## Consequences

- `state/followup.sqlite3` moves to version 2 in place (`migrate`); the
  prototype's empty `actions`/`leases`/`observers` tables are dropped, its
  tickets and events kept. Config moves to schema 2 without changing scope or
  authority.
- `business_writes_enabled` stays false until the owner turns it on; the Codex
  automations and the hook are deleted only after the owner agrees.
- Shopee-specific readers (skynet-base, DW helper) stay in the skill, found as
  a sibling skill rather than through a Codex path.
