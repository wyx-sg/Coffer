# Memory

Every agent you run keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex distils its own work into task groups and a profile. Both do it well, and neither leaves its own directory — so you end up teaching each agent what the other already learned this morning.

**Memory** is Coffer reading those native memories, normalising them into one set of facts partitioned by project, and handing each agent back what it does not know. The whole layer answers to one rule: **Coffer aggregates memory, it does not own it.** Nothing here writes into an agent's own memory files, ever. Everything under `~/.coffer/memory/` is *derived* — delete the directory, run a sync, and the same facts come back — which is exactly what makes it safe to rewrite aggressively.

## Memory is not knowledge

[Knowledge](/guide/knowledge) holds what you or an agent **wrote down about the world**: a platform's API contract, a service's owner, an uploaded PDF. Memory holds what agents **learned while working**: your preferences, a project's decisions, a trap already hit. They differ in every dimension that shapes a design, which is why they are two layers rather than one store with a flag. Knowledge comes from you and is the only copy of itself, so tidying it archives every prior revision and an agent pulls from it when it reaches. Memory is aggregated read-only from your agents, so losing it costs nothing, a fact can be superseded by a later one that contradicts it, and it is **pushed** — a budgeted digest arrives at session start rather than waiting to be asked for.

## Where the facts come from

A sync reads every **registered and enabled** agent, from a path under that agent's own registered `config_dir` (`~/.claude`, `~/.codex`, or wherever you pointed it). Two readers exist today:

- **Claude Code** — one Markdown file per fact under `<config_dir>/projects/<project>/memory/`. Its frontmatter already carries the fact's `name`, `description` and `metadata.type`, so nothing is derived. Claude Code's own `MEMORY.md` index is skipped, and so is anything typed `reference`: that is knowledge the agent wrote down about the world, not something it learned, and it belongs to the other layer.
- **Codex** — `<config_dir>/memories/MEMORY.md`, whose task groups each record the working directory they apply to, plus the distilled profile beside it at `memory_summary.md`. A group's user preferences, reusable knowledge and failures become facts; its own rollout references and roll-up sections do not.

Coffer reads **no transcripts, rollouts or raw capture files** — both agents already distil their own, better than Coffer would, and this layer starts from that output. A source file whose content hash has not changed since the last pass is not read at all, so a pass over an idle machine parses nothing. If one agent's format changes under Coffer, that reader fails loudly and *in isolation*: the failing source is reported by path, the other agent's pass still completes, and facts from earlier passes are left standing rather than deleted.

## Partitions

A partition is a top-level directory under `~/.coffer/memory/` and one `memory` Resource. There is exactly one per project, plus one named `global` — no other axis exists. A project partition is named from **its project root's own directory name**, never an opaque id: `/Users/you/work/coffer` becomes `coffer`. Two projects that share a directory name are told apart by prefixing a parent segment — `work-api` and `personal-api` — because a number would tell you nothing. The absolute root is recorded on the Resource and restated in the partition's `README.md`, so the folder explains itself to anyone browsing it.

`global` is for facts about the person rather than a project: preferences and standing instructions, which go there whichever project they were learned in, as does anything whose project root *is* your home directory. Partitions are created by aggregation, never by you and never by an agent's working directory.

## Run a sync, then look

The daemon runs a pass on its own interval and one immediately at startup, so there is usually something to look at already. To force one:

```bash
coffer memory sync
```

```json
{
  "partitions": ["coffer", "global"],
  "facts_written": 62,
  "sources_read": 9,
  "sources_skipped": 141,
  "failures": []
}
```

```bash
coffer memory partitions
coffer memory facts coffer
coffer memory fact coffer python-lockfile
```

```
Memory partitions
name     facts   project root
coffer      48   /Users/you/work/coffer
global      14
```

`fact` prints the fact's own words — the source's, never a paraphrase; summarising happens in the derived digest — plus every origin: which agent, and the absolute path of the native file it came from. So a fact that looks wrong is always traceable back to the thing that said it.

Two agents that recorded the same thing produce **one** fact with two origins, not two facts. That merge only fires on an exact signal (the same body text, or the same type, partition and title); anything softer is left to the organise pass, which can weigh a judgement call.

## A partition is a folder

You can read one as exactly that, with the same two verbs `coffer knowledge` uses:

```bash
coffer memory ls coffer
coffer memory read coffer facts/python-lockfile.md
coffer memory read coffer README.md --json      # with absolute paths for an editor
```

`ls` prints the whole tree rather than one level, because a partition is two levels deep by construction:

```
~/.coffer/memory/<partition>/
  README.md          the partition, and the project root it was named from
  summary.md         the digest organise writes — one line per fact, for you
  facts/<slug>.md    one fact, frontmatter first
```

Each fact file's frontmatter carries its title, description, type (`user`, `feedback` or `project`), its origins, when Coffer captured it, and a status of `active` or `superseded`. Both commands are read-only, and so is the web UI's file pane — not a missing feature: the tree is derived, so an edit here would survive only until the next pass. If a fact is wrong, fix it where it came from.

## The organise pass

Organise merges what two agents said twice, marks a fact superseded when a later one contradicts it, flags a pair it cannot settle as a conflict, and rewrites the partition's `summary.md`. That file is for **you** — it is what you read when you open the folder; delivery does not read it back, it renders the same lines from the same code against a token budget, so the file and the digest an agent receives can never say the same fact two different ways. It never edits a fact's body and never deletes one — a "duplicate" enriches the survivor's origins and marks the other superseded, so both files stay on disk.

```bash
coffer memory organize coffer
```

Only one pass per partition may run at a time. A second request while one is in flight is **refused** (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued: the pass rewrites the whole directory, so two of them are two writers, not one faster organise.

With no internal model connection configured the pass still writes a usable digest, mechanically — facts grouped by type, newest first, one line each. What you lose is the merging and the supersession, not the feature.

## What an agent actually receives

At session start, a few hundred tokens — 600 by default:

- **L0**, always: what is known about you, what this project's memory holds, and how to ask for more.
- **L1**, when it fits: the current project's facts, one line each.
- **L2**, on request: `coffer__recall`, the one MCP tool this layer adds.

The budget is spent on `global` facts about you first and then the project's most recent, so a trim drops the oldest rather than an arbitrary set, and the closing line is reserved before any fact line is considered — when facts are left out, the payload always says how many and how to reach them. See exactly what an agent would get:

```bash
coffer memory context --agent claude-code --cwd "$PWD"
```

`coffer__recall` takes a word or phrase, spans only the partitions the calling agent is scoped to, and returns matching facts **whole**, with their origins. Matching is a case-insensitive substring scan over each fact's body, then its title and description — no score, no ranking, no model involved, nothing sent anywhere. Give it a distinctive phrase rather than a whole question. There is no `remember` tool: an agent records something by recording it the way it already does, and Coffer reads that on its next pass.

**A channel-driven turn needs no setup at all.** Coffer composes that turn's system prompt itself, so the digest travels with it.

## Installing delivery

For an agent you drive yourself, the digest arrives through that agent's own hook mechanism, and installing one writes a line into that agent's **settings** file. So Coffer never does it silently — it is an explicit act, per agent:

```bash
coffer memory delivery                      # who has it, who does not
coffer memory delivery-install claude-code
coffer memory delivery-remove claude-code
```

```
Memory delivery
agent         installed   command
claude-code   True        : coffer-memory; coffer memory context --agent claude-code --cwd "$PWD"
codex         False       : coffer-memory; f="${TMPDIR:-/tmp}/.coffer-memory-fired-$PPID"; …
```

Claude Code gets it on `SessionStart`, in `settings.json`, matching all four ways a session begins. Codex has no session-start event at all — its five hook events are `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop` and `UserPromptSubmit` — so it gets the earliest of those with a once-per-session guard, a lock file keyed on the invoking process, and the digest arrives once rather than on every prompt.

Every entry carries Coffer's own marker (`: coffer-memory;`), so installing twice leaves one entry and removing takes out only Coffer's; every hook you or another tool wired onto the same event is left exactly as it was. The command itself is built to fail quietly: if the daemon is not running, or is slow to answer, `coffer memory context` prints nothing and exits 0 rather than breaking a real session.

### Installed is one question; fired is another

The delivery listing answers exactly one thing — installed or not. It carries **no last-fired timestamp**, on purpose. Whether the hook has run is not a property of the agent but a stream of events, and it is recorded as one, on the vault-wide audit surface:

```bash
coffer audit list --event-type memory_delivery_fired --name claude-code
```

That split is a reaction to a specific failure. Coffer shipped a session-context injection layer once, it worked, it was never actually installed on the maintainer's own machine, and nothing said so for two months. The fix is not a warning light on the agent's page: a hook installed a minute ago has legitimately never fired, and a surface that flags that is crying wolf about its own normal state. The fix is that every fire is an event you can go and read. `memory_aggregated`, `memory_organised`, `memory_delivery_installed` and `memory_delivery_removed` are recorded the same way, each with the actor that caused it — so a scheduled pass is distinguishable from one you asked for.

## Reach, and deleting a partition

A partition is a Resource, so the framework's per-agent reach applies. Its default scope is the set of agents it was aggregated from — memory flows back to its own sources with no setup — and narrowing it is yours to do; a later pass never overwrites your choice. Scope is enforced on delivery *and* on recall.

```bash
coffer scope show memory:coffer
coffer scope set memory:coffer --agents claude-code
coffer scope clear memory:coffer
coffer resource delete memory:coffer        # lifecycle is a Resource concern
```

Deleting takes the directory with it, and is safe in the sense that matters here: the next sync rebuilds it from the agents' own files.

::: tip The facts stay on this machine
[Sync](/guide/sync) mirrors the knowledge and skills trees between machines. It carries **nothing** of memory: not the tree under `~/.coffer/memory/`, and not the partition rows either — `memory` is the one resource kind that does not converge. These facts are aggregated from the agents installed on *this* machine, so each machine derives its own from the agents it actually has, and a partition published to another would arrive there naming a project root that machine may not have, with no facts behind it, until its own next pass recomputed it away. Losing the tree costs nothing — the sources it came from are still in the agents' own directories.
:::

## The unattended passes

Aggregation and organise both run on a timer and both default to **on** — unlike knowledge's tidy, which rewrites your only copy and stays off until you switch it on. These two only read the agents' files and write derived ones. Aggregation also runs a catch-up pass immediately at startup, because a daemon that has just started is when its picture of the agents is most stale. Both switches and both intervals live on **Settings → Engine**, alongside knowledge's tidy, and are read per pass rather than at boot — a change takes effect without restarting the daemon.

## The CLI

| Area | Commands |
| --- | --- |
| Partitions | `partitions` · `facts` · `fact` |
| Files | `ls` · `read` |
| Passes | `sync` · `organize` |
| Delivery | `delivery` · `delivery-install` · `delivery-remove` · `context` |

## The REST surface

| Route | Purpose |
| --- | --- |
| `GET /api/v1/memory/partitions` | Every partition, with its root and fact count. |
| `GET /api/v1/memory/partitions/{name}/facts` | The facts in one partition. |
| `GET /api/v1/memory/partitions/{name}/facts/{slug}` | One fact, with origins and conflicts. |
| `GET /api/v1/memory/partitions/{name}/files` | The partition's own directory, as a tree. |
| `GET /api/v1/memory/partitions/{name}/files/content?path=…` | One file out of it. |
| `POST /api/v1/memory/sync` | Run aggregation now. |
| `POST /api/v1/memory/partitions/{name}/organise` | Run the organise pass now. |
| `POST /api/v1/memory/context` | Compose the session-start payload. |
| `GET /api/v1/memory/delivery` | Per-agent installation state. |
| `POST /api/v1/memory/delivery/{agent}/install` | Install the hook. |
| `DELETE /api/v1/memory/delivery/{agent}` | Remove it. |

The file family is read-only — a write is refused with 405, and a path escaping the partition with `MEMORY_UNSAFE_PATH`. Deleting a partition is the kind-agnostic `DELETE /api/v1/resources/memory/{name}`; there is no memory-specific route for it.

These routes are the *owner's* view and are unscoped. Scope is enforced where a real agent's session reaches — `POST /context` and `coffer__recall`.

## In the web UI

Memory is one page under **Resources**. `/memory` lists partitions as a table — the same table whether you have a hundred or none — with each row's project root, fact count and reach control, and **Read from agents** in the header to run a sync. `/memory/:name` opens one partition as a file tree with a read-only preview beside it, plus the two acts that belong to the partition as a whole: where it reaches, and **Organise**.

There are no per-fact actions anywhere: a partition is a folder of derived Markdown, and the surface that browses it says so by looking like one. Delivery is **not** on this page. It writes one agent's settings file, so it lives on that agent's own detail page, under its Memory tab — beside the read-only view of that agent's native memory stores, which Coffer shows you and never writes.

[Channels →](/guide/channels)
