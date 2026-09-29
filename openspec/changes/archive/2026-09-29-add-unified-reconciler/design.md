## Context

The ADR [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database, Comparing Parameters](../../../docs/decisions/one-level-triggered-reconciler-compares-parameters.md)
chooses one reconciler over six per-kind heals. The agents' projection registry
([Agent Mechanisms Are Optional Facets on the Descriptor](../../../docs/decisions/agent-mechanisms-are-optional-facets-on-the-descriptor.md))
names the targets: the MCP entry, skill links, the provider projection and the
delivery hook. The channel runtime keeps its own two-second loop for adapter
lifecycle, as the ADR says.

## Goals / Non-Goals

**Goals:** one loop, one target contract, parameter equality everywhere, one
dry-run, one drift read, the audit rule, the attention read model, and removal
of every per-kind reconcile path the loop replaces.

**Non-Goals:** filesystem watching (the ADR keeps it an optional hint source
for later), an event stream to the UI (S-4), new targets beyond the four the
registry lists.

## Decisions

- **Shape.** `domain/reconcile.py` holds the pure vocabulary (items with
  parameters, differences, decisions, outcomes, the diff).
  `application/reconcile/` holds the target protocol, the reconciler and its
  pass steps, and the hinting repository wrapper. Each target lives in its
  kind's package and imports only kind-agnostic code, so the cross-kind fence
  is unchanged.
- **Desired from Coffer's state, membership from the user's acts.** For the MCP
  entry and the delivery hook, whether an agent is connected is recorded by the
  entry itself (connect / disconnect are explicit acts), so the target wants an
  entry where one exists — judged by its parameters — and never adds one where
  none is. The delivery hook is installed where missing only when a pass runs
  for the `memory` switch or a person applies it.
- **Direction policy reads the trigger.** A few differences are repairable on
  one warrant and only reportable on another: a provider projection absent
  while its flag is set is projected after an import or on a person's request,
  and otherwise corrected by clearing Coffer's own flag; keys no active
  connection claims are removed after an import or on request, and otherwise
  reported. Triggers are `boot`, `period`, `hint`, `change`, `import`,
  `switch`, `manual`.
- **Front-door writes run the pass synchronously.** A skill enabled, rescoped
  or imported, an agent registered, enabled or moved, the builtin skill seeded:
  each calls the skill-link target's pass (`change`) before answering, so the
  delivery is visible when the write returns. Every resource write also hints
  (`Changed(kind, uid, rev)`), which brings the next pass forward for targets
  that follow that kind after a 0.5 s settle.
- **Hold.** A provider switch and a sync round's apply are several writes; each
  runs inside `Reconciler.hold()`, which keeps every other pass out and lets the
  holder's own pass run inside. It is re-entrant inside a pass, so a repair that
  goes through a held service cannot wait on itself; a task the holder spawns
  does not inherit it.
- **Audit and undo.** A target's apply writes and returns its audit event and
  an undo; the reconciler records the event and, if that fails, runs the undo
  (restore the prior content, which is what the `.bak` holds, or delete a file
  the write created) and fails the item.
- **Period.** 60 s. Measured on 2026-09-29 by
  `backend/tests/integration/perf/test_reconcile_pass_cost.py` — a full pass
  over two agents, twenty skills, a provider connection and both hooks costs
  about 27 ms (median, and the same for the dry-run plan) — so the period is
  chosen by how long drift may stand unnoticed, not by cost. A pass slower than 2 s is logged.
- **Read models.** `GET /reconcile/plan`, `POST /reconcile/apply` and
  `GET /attention` belong to `resource-framework`, the one capability whose
  scope is already cross-kind; `coffer drift list|repair` and
  `coffer attention` are their CLI counterparts. The attention list's drift
  source leaves out a repairable difference no writing pass has visited yet —
  the next pass repairs it without anyone.

## Risks / Trade-offs

- A periodic pass reads files on a timer → measured and bounded above.
- An attention signal nothing records (a provider key the endpoint rejected, a
  Telegram token refused) has no source; the list reports only what the backend
  knows, and a new source is the extension point.
