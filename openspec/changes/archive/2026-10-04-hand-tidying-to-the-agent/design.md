## Context

Knowledge curation and the memory distil pass were Coffer's two unattended
model consumers. They were reached through the internal default connection,
which is a provider flagged `internal_default` plus a model in
`state/settings/internal-engine.json`. Both already had a mechanical path for
when no model was configured. This change makes the mechanical path the only
one, and moves the judgement into the skill the agent already loads.

## Goals / Non-Goals

**Goals:** no Coffer-run model call over knowledge or memory; the agent tidies
on one click; every mechanical duty keeps working; transcription untouched.

**Non-goals:** renaming the `internal-engine` settings document or route
family (it still holds the timeout, the speech-to-text model and the upkeep
switches); scheduling agent runs; changing aggregation or delivery.

## Decisions

### 1. The judgement lives in `coffer-guide`, not a new skill

The guide is already delivered to every agent, and its resident description
is the only always-paid cost. One skill keeps that cost single. The knowledge
span gains "Writing something down" (six rules, straight into documents) and
"Tidying a collection". The memory span gains "Tidying memory". The
description lead adds "how to write and tidy knowledge" and "how to tidy them"
(memory notes), so a request to 整理 matches.

### 2. Tidy is a hand-off that sends itself

The backend owns the prompt, as with every hand-off. Two endpoints return it:
`CollectionOut.tidy_handoff` (knowledge) and the partition's `tidy_handoff`
(memory). Both are `HandoffOut` and both are rendered by `domain/handoff.py`.
The task names the collection or partition and its absolute path, and says to
follow the coffer-guide section. The facts carry the path and the document or
note count.

Each list page also has **Tidy all** in its header, backed by
`GET /api/v1/knowledge/tidy-handoff` and `GET /api/v1/memory/tidy-handoff`. That
prompt names the root and every collection or partition, with its path and
count, and asks the agent to tidy them one at a time in a single conversation.

In the web UI, **Tidy** uses the existing hand-off draft route with
`autoSend: true` in the location state. `useChatController` sends the seeded
prompt once on the default managed agent and lands on the new conversation.
Every other hand-off keeps the draft-only behaviour. With no managed agent
available, the button offers Copy prompt only, through the existing
`AgentHandoff` fallback.

The decision to send without asking follows from the button itself. The person
pressed Tidy, the prompt only edits Coffer's own files, and both trees are
recoverable: knowledge has its git history, and memory is a derived tree
rebuilt from the agents' own memory.

### 3. Nothing tidies unattended

Tidy runs only when the person presses the button. Scheduling agent runs
would need loop-proofing against Coffer's own hooks, would spend the person's
quota without their knowledge, and would leave conversations nobody started.
The mechanical passes stay on their timers: aggregate, distil (now mechanical)
and the knowledge sweep.

### 4. Memory retirement by frontmatter

An agent cannot compute raw entry ids, and a deleted note comes back because
its origins become undistilled again. So the agent marks a note instead:
`retired: <reason>`, plus an optional `replaced_by: <slug>`. The distil pass
(mechanical) handles marked notes before it computes undistilled entries. For
each marked note it appends a `RETIRED.md` record with the note's origin entry
ids, the reason and `replaced_by`, deletes the file, and re-renders the index.

A merge needs no new mechanism. The agent appends the merged note's `origins`
to the survivor's and deletes the merged file. Those entries are already
accounted for by the survivor's origins.

### 5. Knowledge material is promoted at once; `.inbox/` stays as a drop zone

`submit()` always promotes, as the no-model path did. An upload
becomes a document at the collection root, with frontmatter filled from its
opening prose.

A file dropped into `.inbox/` by an agent outside Coffer, by another machine
or by an older guide is adopted and promoted by the next sweep. This is the
existing intake, and it also clears the items already waiting on existing
vaults.

The inbox waiting views go: the tree node, the waiting list, `pending_count`,
the upload's `pending`, and Recent changes' waiting items. Nothing waits longer
than one sweep. `.inbox/` becomes an ordinary hidden entry.

### 6. The knowledge sweep keeps three mechanical duties

`curate_worker` is replaced by a sweep worker with three duties:

- re-render and re-seed the guide;
- adopt and promote `.inbox/` files;
- commit edits found on disk as `disk` writes.

The curation lock and hold that coordinated with sync rounds go, because the
sweep writes only what it promotes and that write goes through `VaultWriter`
like any other.

`local/curation.json` and `curated_at` ("Last curated") are deleted, because
they recorded which content a pass had settled.

### 7. Retired stored values are accepted and ignored

A provider file may still carry `internal_default`. It is added to
`_RETIRED_CONFIG_KEYS` and dropped on the file's next write, as `agent.effort`
was. In `internal-engine.json`, `model`, `curate_owner_machine_id` and
`upkeep.curate` are ignored on read and dropped on the next write of the
document.

Historic `curation` writer commits, pass metadata and the `knowledge_curated`
and `provider_internal_default_set` audit rows are history. They keep
rendering with their labels.

### 8. The timeout moves next to speech-to-text

Transcription is now the only model call Coffer makes. The per-call timeout
row moves into the Speech-to-text section of Settings › General, and the
"Coffer's model" engine picker is deleted.

## Risks / Trade-offs

- Notes duplicate across agents until someone presses Tidy. The index is
  budgeted, so delivery truncates sooner. This is accepted: the person sees
  the duplicates and the button.
- An agent can tidy badly. Knowledge is recoverable through History and
  Restore; memory can be rebuilt by deleting the derived tree.
- An agent that drops a note's `origins` while merging brings the merged note
  back on the next update. The guide states the rule; the failure is visible
  and harmless.
