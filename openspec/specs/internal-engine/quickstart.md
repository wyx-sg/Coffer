# Quickstart — Coffer's Internal Engine

Coffer does some work itself: it aggregates what your agents have learned, lets
a model rewrite that digest, tidies your knowledge files, resolves a sync
conflict and transcribes a voice message. This is where you say which model does
that work, and what it is allowed to do while you are not watching.

None of it is required. With no engine configured, every one of those passes
quietly does nothing and the rest of Coffer works exactly as before.

## Prerequisites

- Coffer's daemon is running (`coffer daemon start`, or `coffer open`).
- At least one LLM connection exists (see spec
  [provider-switching](../provider-switching/quickstart.md)). A local `ollama`
  endpoint is a good one to give Coffer: it costs nothing and reaches no agent.

## Point Coffer at an endpoint

The engine borrows a connection. Exactly one connection at a time is the one it
borrows:

```bash
coffer provider internal-default local-ollama
```

## Choose the model it thinks with

```bash
coffer engine model set qwen2.5:7b
coffer engine model show
```

The model is Coffer's own setting, not a field on the connection — which is why
changing the connection can drop it:

```bash
coffer provider internal-default my-openai
coffer engine model show     # empty again, unless my-openai curates qwen2.5:7b
```

Nothing is probed to decide that. A connection's curated model list is its own
catalogue, so a model on it is kept; anything else is dropped rather than left
aimed at an endpoint that has never heard of it.

To stop Coffer using a model at all:

```bash
coffer engine model clear
```

Every pass then becomes a no-op. Nothing errors, and nothing warns you on every
turn.

## See what Coffer does unattended

Three passes run on a timer:

| Pass | What it writes | Ships |
|---|---|---|
| `aggregate` | the derived memory tree, read from the agents' own memory | ON |
| `distil` | a rewrite of that derived digest | ON |
| `tidy` | **your own knowledge files** | OFF |

```bash
coffer engine upkeep list
```

Each row says whether the pass is on, the interval you chose, and — when you
have chosen none — the default that runs instead. The default lives with the
pass, so it is reported rather than copied into your vault.

## Change one pass

```bash
coffer engine upkeep set tidy --on --interval 21600   # every six hours
coffer engine upkeep set distil --off
coffer engine upkeep set aggregate --default-interval
```

One pass per command, on purpose: the other two are left exactly as they stand,
including on a second machine that may be changing them at the same moment.

A running daemon picks the change up on its own — no restart. An interval below
the floor, or a pass name Coffer does not run, is refused.

## From the web UI

**Settings → Engine** has the same two halves: a card for the connection and the
model, and a card with one row per pass. Edits save as you make them; there is
no Save button. The `tidy` row carries a line saying what it rewrites, because
it is the one pass whose output is not reproducible by deleting and re-running.

## Over HTTP

```bash
# What Coffer is set to
curl "$COFFER_URL/api/v1/internal-engine-config" \
  -H "X-Coffer-Token: $COFFER_TOKEN"

# Set the model
curl -X PUT "$COFFER_URL/api/v1/internal-engine-config" \
  -H "X-Coffer-Token: $COFFER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen2.5:7b"}'

# Switch one pass off
curl -X PUT "$COFFER_URL/api/v1/internal-engine-config/upkeep" \
  -H "X-Coffer-Token: $COFFER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pass": "tidy", "enabled": false}'
```

## Across your machines

These settings converge with the rest of your vault as
`state/settings/internal-engine.yaml`. Coffer's passes behave the same
everywhere only when they run on the same model, and switching a rewriter off is
exactly the decision a second machine must not be left out of.

A machine that has chosen nothing publishes no document at all — the tree holds
one exactly while somebody has made a choice. Deleting it means "back to the
defaults" on every machine.

## Troubleshooting

**A pass never runs.** Check three things in order: `coffer engine model show`
(no model = every pass is a no-op), `coffer engine upkeep list` (the switch),
and whether a connection is flagged (`coffer provider list --json | jq
'.providers[] | select(.internal_default)'`).

**The model went blank on its own.** You changed which connection the engine
borrows, and the new one does not curate the model you had. Pick one it serves.

**A new interval seems not to take effect.** It takes effect within one slice of
the running wait, not instantly — but well inside the old interval. If nothing
changes after that, the pass's switch is off.

**Tidy rewrote something you wanted kept.** `tidy` ships OFF for that reason;
switch it off again with `coffer engine upkeep set tidy --off`, and recover the
file from your vault's history (spec
[vault-sync](../vault-sync/quickstart.md)).
