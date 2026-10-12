# The Memory Page Lists the Memories by Scope; the Sync Shows Only When It Needs the Person

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [Sync Memory Into Each Agent's Own Memory Through a Hub in the Vault](sync-memory-into-each-agents-own-memory.md), [Every Web UI and Desktop Operation Has a `coffer` Command Over the Same Route](command-line-parity-with-the-web-ui.md), research note [agent memory § Memory page layouts](../research/agent-memory.md#memory-page-layouts), spec memory "Manage memory sync in the web UI and on the command line", OpenSpec change `lay-out-memory-page-by-scope`

## Context

The memory sync (hub in the vault, copies written into each agent's own
memory) shipped with a Memory page that laid out the sync's machinery:
under the header, one warning panel for each source the last sync could not
read and each memory it withheld, a table for a pending preview (per agent and
project, how many copies would be written, updated and removed), a table of
the hub's projects (key, checkout here, count, origin agents), and a table of
this machine's agents (copies written, own memory switch, own curation switch
with a hint, **Curate now**), with Codex's "imports Claude Code's memories
itself" switch underneath. A project opened a second page whose table had one
column per local agent for the copy's state.

The maintainer found it confusing. Rendering the page with realistic data
showed why:

- **No memory was visible.** The first screen was tables of counts. A memory
  took two clicks, and even then only its title and a truncated description:
  nothing in the product showed a memory's text.
- **The vocabulary was the implementation's.** Hub, publish, copy, held back,
  origin, own memory, own curation — the person had to learn the sync's model
  before the page made sense.
- **Problems had no hierarchy.** Up to three tall panels stacked above the
  content, so a machine with one unreadable file and a pending preview showed
  nothing but warnings above the fold.
- **The per-agent copy columns were mostly grey.** Copy states matter only when
  something is off (a copy waiting, edited or removed by the agent); otherwise
  every cell says "written" or "its own".
- **Agent settings scaled with the number of agents.** A row (and, in an early
  redraw, a chip) per agent on the Memory page grows with every agent Coffer
  supports, and the settings it shows belong to the agent, not to the memories.

Research into how comparable products present memory
([research note](../research/agent-memory.md#memory-page-layouts)): ChatGPT,
Gemini, Claude.ai, Windsurf and Cursor make the list of memories the page and
put each on/off control in one line; coding tools (Claude Code `/memory`,
Windsurf, Copilot, VS Code) group by scope — global vs project — as sections,
not as a column; OpenMemory, the closest to a multi-tool store, shows the
source app on each memory and keeps per-app controls on a separate Apps page;
Copilot is criticised for putting the switch on a different page from the
list, but it puts the switch with the tool, not with each memory. No product
was found that shows per-item sync state well; OpenMemory's access log comes
closest.

## Options Considered

### Option A — Memories by scope, the sync only when it needs the person (chosen)

The page is a split view: scopes on the left (global memories, then projects
by short name with counts, projects not checked out on this machine in their
own group), the open scope's memories on the right (title and description,
type, origin agent and machine, last change; search and type / source
filters). A copy state appears on a memory's row only when it is worth a look
(waiting for the next sync, edited or removed by the agent's curation). A
memory opens in the shared drawer: first where each local agent holds it — one
line per agent with the copy's state, the file and Open / Reveal — then its
text, read only. Everything that waits on the person (a preview to confirm,
an unreadable source, a withheld memory, an agent Coffer cannot write into) is
one banner whose **Review** opens a drawer; a preview's groups are collapsed
to their counts and open down to each memory (a group that removes anything
starts open). Each agent's own memory switch, curation switch, copies and
**Curate now** move to that agent's Memory tab, with Codex's import switch.

- **Pros:** the memories are the page, as in every product surveyed; scope is
  grouping, as in coding tools; the sync stays quiet until it needs the person;
  the page's layout does not change with the number of agents; agent settings
  sit with the agent, beside the agent's own memory files; the drawer is the
  first place the product shows a memory's text.
- **Cons:** the largest change of the three — a new route shape, a detail
  route and command, the preview's per-memory items on the wire, the agent tab;
  the per-agent overview of copies is no longer on one screen (it is one tab
  per agent).
- **Why it wins:** it removes the causes, not the symptoms: nothing on the first
  screen needs the sync's model to read, and nothing grows with the number of
  agents.

### Option B — Keep the structure, split it into tabs

Three tabs: Memories (the projects table, opening the per-project page),
Agents (the agents table and the Codex switch), Problems (failures, withheld,
preview).

- **Pros:** small change; each tab is less crowded.
- **Cons:** a memory is still two clicks away and its text still nowhere; the
  per-agent copy columns stay; the Agents tab still grows with every agent and
  still shows settings that belong to the agent.
- **Why it loses:** it tidies the machinery without making the memories the
  page.

### Option C — Change only the wording and the warnings

Drop "hub", "copy" and "publish" from the copy, merge the warning panels into
one, and show only notable states in the per-project table.

- **Pros:** smallest change; no route or wire change.
- **Cons:** the page still opens on tables of counts; agent settings still
  scale with agents; still no memory text.
- **Why it loses:** the confusion came from what the page shows, not only from
  how it is worded.

### Agent settings: chips on the Memory page vs the agent's Memory tab

Within Option A, the first redraw kept one chip per agent under the header,
each opening a popover with its switches and **Curate now**. It was dropped:
chips grow with the number of agents, and the settings are the agent's.
The Memory page instead counts an agent Coffer cannot write into among the
things that need the person, and links to that agent's Memory tab.

## Decision

The Memory page lists the hub's memories by scope: global memories, then the
hub's projects, each opening its memories beside the list (`/memory?scope=`),
and a memory opening in the drawer (`&memory=<id>`) with where each local agent
holds it first and its text below. Copy states show on a memory only when they
are worth a look. What waits on the person is one banner and one drawer. Each
agent's own memory, curation, copies, **Curate now** and (for Codex) the
import switch live on the agent's Memory tab, whose **Open Memory** opens the
page filtered to that agent's memories.

Rules a later change must respect:

- Nothing on the Memory page grows with the number of agents: per-agent
  settings go on the agent's tab; per-agent facts about one memory go in its
  drawer.
- The page still never edits a memory's text; the drawer shows it read only
  and opens the agent's file.
- Every operation stays a `coffer memory` command (`coffer memory show` for
  the drawer).

## Consequences

- New route `GET /api/v1/memory/sync/entries/{entry_id}` and command
  `coffer memory show`; the preview's rows carry each memory they would write,
  update or remove.
- `/memory/projects/<folder>` and `/memory/global` redirect to the scope on
  the Memory page; the separate project page is gone.
- The agent detail page's Memory tab gains a "Memory sync" section (shown while
  the memory feature is on).
- The shared drawer gains **Maximize** / **Restore** so a long memory (or any
  long record) can take the page's width; it already resized by its edge.
- Canvases: Context (Memory boards), Agents (agent Memory tab), Foundations
  (drawer).
