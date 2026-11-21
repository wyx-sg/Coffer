# What Coffer Does for an Agent Follows From Its Facets, and Surfaces Leave Out What It Lacks

**Status**: Accepted
**Date**: 2026-11-21
**Deciders**: Yuxing Wu
**Related**: [Agent Mechanisms Are Optional Facets on the Descriptor](agent-mechanisms-are-optional-facets-on-the-descriptor.md), [Antigravity Joins Coffer Through Its Config Layer Only](antigravity-joins-at-its-config-layer-only.md), [Cursor, OpenCode and DeepSeek Harness Are Supported Agents](cursor-opencode-and-deepseek-harness-are-supported-agents.md), [A Shared Skills Directory Holds One Link for Every Agent That Reads It](a-shared-skills-directory-holds-one-link-for-every-reader.md), research note [multi-agent feature gaps](../research/multi-agent-feature-gaps.md), spec agent-registry "Report what Coffer can do with each agent type", spec skill-manager "Name the agents that also see a skill", spec scheduled-tasks "Manage scheduled tasks from the Scheduled tasks page"

## Context

With six agent types, most features exist for only some of them. Antigravity
has no driver (its terms do not allow running `agy` inside another tool on a
personal plan) and no provider projection (it runs only Google's models).
Cursor cannot be pointed at a custom model endpoint. Cursor, OpenCode and
DeepSeek Harness have no driver, plugins or hooks yet. Every new type will
lack something.

Until now agent-registry said there was no per-facet support state and that a
facet a type could not support was a reason not to add the type. The backend
already kept per-agent mechanisms in optional facets, and a build gate kept
other code from branching on the agent type. The web UI had no such rule: it
named `claude_code` and `codex` in about twenty files, so the scheduled-task
picker offered Codex on a Mac without it, and every new type meant a search
for lists of names.

Three questions follow: how the code says what a type supports, how a
surface shows a feature a type lacks, and where the reason is given. Skills
add a fourth: several agents read the same skills folders, so a scope naming
one of them cannot keep a skill from the others.

The [research note](../research/multi-agent-feature-gaps.md) finds the same
pattern across ACP, Rulesync, AgentsMesh, CC Switch, LiteLLM and VS Code: the
integration declares what it can do, an omitted capability is unsupported,
entry points that do not apply are absent, and the explanation lives in one
place.

## Options Considered

### How support is expressed

#### A — A `features` list derived from the descriptor and its bound facets (chosen)

`domain/agent/features.py` names `mcp`, `skills`, `provider`, `chat`,
`sessions`, `plugins` and `hooks`; each follows from a facet or descriptor
value (a driver means `chat`, a provider projection `provider`). Agent and
type rows carry the list; surfaces render from it.

- **Pros.** Cannot claim what the code does not do: no driver, no `chat`. A
  type gains a feature the day its facet is bound, with no surface change.
  Matches ACP's "omitted means unsupported".
- **Cons.** The frontend needs a sweep once, and a gate so names do not grow
  back.

#### B — A hand-written support table on each descriptor

- **Pros.** One glance shows everything.
- **Cons.** A second statement of what the facets already say; the two drift
  (marked supported, facet not bound yet).

#### C — Keep naming agents in the web UI

- **Pros.** Nothing to change.
- **Cons.** Every type means editing a list of names in many files, and a
  missed one shows a choice that fails, as the scheduled-task picker did.

#### D — Ask each agent at runtime, as ACP does at `initialize`

- **Pros.** Exact for the installed version.
- **Cons.** Claude Code and Codex speak no such handshake; a protocol for a
  handful of static facts is more machinery than the facts.

Graded levels (AgentsMesh's Native/Partial) were not taken: a Coffer feature
is either bound or not, and a partial one is the facet's own business (OpenCode
1.x and 2.x MCP shapes are handled inside its MCP entry).

### How a surface shows a feature a type lacks

- **Leave it out (chosen).** A picker lists only agents that can do the thing
  here (for a turn, the agents the turn platform reports available); an agent
  page has no tab, tile or section for what the type lacks. Pages themselves
  stay, so navigation is the same on every machine, and say in an empty state
  when no added agent can do what they need.
- **Disable it with a reason.** Clear with two agents; with six types and
  seven features it is a page of grey rows and repeated reasons. No surveyed
  product does it.
- **Show it and fail on use.** The worst of both: a choice that cannot work.

### Where the reason is given

- **One support table in the agents guide (chosen)**, English and Chinese,
  each gap marked as the product offering no way, its terms not allowing it,
  or Coffer not doing it yet. A test keeps the table equal to the `features`
  the daemon reports, so it cannot go stale. Only "not yet" gaps are work.
- **A reason code per gap on the wire, shown in the UI.** More direct, but
  one more per-type table to keep for every type, for text a person reads
  once.

### Skills folders read by several agents

- **Say who else sees a skill (chosen).** Each type reports the skills folders
  it reads (`skill_dirs_read`: the one Coffer delivers to, then the ones the
  product reads on its own, such as Cursor and OpenCode reading
  `~/.claude/skills`). The reach panel says in one line which added agents
  share a folder and which also see a skill delivered for another.
- **Write each agent's own hiding rule** (OpenCode's `permissions` deny rule
  per skill). Exact for OpenCode only; Cursor's CLI offers no way at all, and
  Coffer would keep a per-skill rule list in another product's config in step
  with every scope change.
- **Drop per-agent scope for skills.** Honest, but loses the separation that
  still works between Claude Code and Codex, which read different folders.

## Decision

What Coffer can do with an agent type is its `features`, derived from the
descriptor and its bound facets (option A); a type may lack any mechanism
facet its product does not offer or permit. Surfaces leave out what a type
lacks, and pickers offer only agents that can do the thing here. The agents
guide's support table is the one place a gap is explained, kept equal to
`features` by a test. The web UI names an agent type only in its agent modules
and in the few files that hold a per-agent value the daemon does not serve,
each listed with its reason in `scripts/check_frontend_agent_types.py`, run by
`make lint`. A skill's reach panel names the added agents that also see the
skill, from each type's `skill_dirs_read`; Coffer writes no hiding rule into
an agent's config.

## Consequences

- agent-registry no longer says a missing facet is a reason not to add a
  type; it keeps the rule that a type must be exercisable on a real install
  (the `agent-cli` CI job), which is where the cost of a type now lies.
- A type that gains a driver appears in chat, channel and scheduled-task
  pickers without a web UI change.
- Hand-off agents, resume commands, plugin layouts and a few other per-product
  values stay in the web UI, listed in the gate; serving them from the daemon
  is left until a third type needs one.
- A skill scoped to Codex is seen by Cursor, OpenCode and DeepSeek Harness when
  they are added, and one scoped to Claude Code by Cursor and OpenCode; the
  reach panel says so.
