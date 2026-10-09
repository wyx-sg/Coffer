# Names Visible to Agents Are Fixed

**Status**: Accepted
**Date**: 2026-09-30
**Deciders**: Yuxing Wu
**Related**: [A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md), [Kind Plug-in Contract](kind-plugin-contract.md), [Tool Overload: List a Usage-Ranked Slice, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), [Skills Reach an Agent as a Directory Link](cross-platform-skill-delivery.md), research note [MCP gateways](../research/mcp-gateways.md), spec resource-framework "Treat a resource's name as a mutable label", spec resource-framework "Carry an optional editable title on the kinds that have one", spec agent-registry "Keep one agent per type, named by it", spec mcp-gateway "Manage MCP servers as resources", spec mcp-gateway "Flag tools whose client-visible name is too long", spec skill-manager "Keep one master folder per skill", OpenSpec changes `reshape-cli-and-mcp-surface` and `one-agent-per-type-and-no-titles`

## Context

[A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md)
split identity from label: the `uid` is what every surface, reference and
synced document holds, and the `name` became a label that any kind could
rename through the ordinary `PATCH`. That was right for everything Coffer's own
surfaces are the only readers of. It was wrong for two kinds, because their
name is not only Coffer's label — it is quoted in files Coffer cannot see.

- **An MCP server's name is part of every tool name an agent is given.** The
  gateway advertises each upstream tool as `<server>__<tool>` and resolves an
  incoming call by that prefix (`application/mcp/gateway_handlers.py`). The
  client adds its own prefix on top, so Claude Code shows the tool as
  `mcp__coffer__<server>__<tool>`. That string is what the user writes into the
  agent's permission rules (`allow: ["mcp__coffer__github__create_issue"]`),
  and what skills and project instructions tell the agent to call. A rename changes every
  one of those strings at once, and nothing that holds the old one is told.
- **A skill's name is the directory an agent loads it from and the name it
  invokes it by.** The master folder, every delivered link and the SKILL.md
  `name:` all carry it ([Skills Reach an Agent as a Directory Link](cross-platform-skill-delivery.md));
  other skills and instructions reference it by that name.

The rename worked inside Coffer — the uid kept the resource, the audit trail and the
synced file intact — and broke silently outside it, in files that are the
user's or the agent's, on the day the user next relied on them.

A second, related limit applies to the MCP server's name alone. Model provider
APIs cap a tool name at 64 characters, and Cursor drops tools whose name
exceeds 60. `mcp__coffer__` (13) + the server name + `__` (2) is spent before
the upstream tool's own name starts, so a long server name leaves too little
for the tools behind it.

How others treat the same name (survey behind this change; the gateway
details are in the [MCP gateways](../research/mcp-gateways.md) research note):

| Product | Server name after registration |
| --- | --- |
| Claude Code (`claude mcp add`) | Fixed; changing it means removing and adding the entry, and the `mcp__<server>__<tool>` names change with it |
| Codex (`[mcp_servers.<name>]`) | Fixed; the name is the TOML table key |
| Cursor (`mcp.json`) | Fixed; the name is the JSON object key |
| VS Code (`mcp.json` `servers`) | Fixed; the name is the JSON object key |
| MCPJungle | Fixed; `mcpjungle register --name` and `server__tool` names |
| IBM ContextForge | Renamable, and the rename re-slugs every federated tool name (`<gateway-slug><sep><tool>`) |
| MetaMCP, ToolHive vMCP | Per-tool overrides (`override_name`, `overrides`) as a separate layer over a fixed server name |

The MCP specification draws the same line for tools, prompts and resources: a
`name` is the programmatic identifier, and an optional `title` is the
human-readable display name. Nobody who displays a friendlier label does it by
changing the identifier.

Once the name is fixed, the question is whether these kinds need a second,
editable label beside it. Coffer tried one: an optional `title` on every
resource, shown in place of the name. Two names for one thing
made every surface decide which to show, and hid the name the user types in the
CLI and the agent quotes in its permission rules. The title has no reader
outside Coffer, and what it was for — saying what the thing is — is already
said by a server's description and a skill's `SKILL.md` description.

Agents raise the same question from the other side. A machine could hold
several agents of one type, each under a name, title and description a person
made up. Nobody runs two Claude Codes from one Coffer, and the chosen name
decided which of two answered for the type. With one agent per type, the type
already is the name.

## Options Considered

### Option A — Fix the name of kinds whose name is visible outside Coffer, with no second label beside it (chosen)

`Kind` gains `name_fixed: bool` (`domain/resource.py`). `mcp_server`, `skill` and `agent` set it. A `PATCH` whose `name` differs from the current one is refused
with `409 NAME_IMMUTABLE` before any other field of the same request is written
(`application/resource_rename_ops.refuse_fixed_name`). The refusal says the
only way to a new name — delete and register again — and what that resets,
from the kind's `name_fixed_resets`: an MCP server's capability toggles and
reach, a skill's enabled flag, scope and deliveries.

`agent` is fixed for a different reason: a machine holds one agent per type,
and its name is derived from the type (`claude_code` → `claude-code`, `codex`)
through `Kind.name_from_config`, so there is no other name it could have.

None of the three carries a display title (`Kind.titled = False`): an MCP
server is its fixed name plus its description, the user's own note; a skill is
its fixed name plus its `SKILL.md` description, the text agents choose it by;
an agent is its type. A non-empty title on these kinds is refused as a
validation error on every surface. `provider`, `channel` and `knowledge` keep
renamable names, because their names appear only on Coffer's own surfaces (or,
for knowledge, in a directory Coffer moves itself through the kind's
`on_rename` hook). `provider` and `channel` keep the optional `title`; a knowledge collection is shown by its folder name beside
a description its README opens with, so it carries none.

- **Pros.** Nothing an agent or a user has written down can go stale because of
  Coffer. Every surface shows the one name the user types and the agent quotes,
  so there is nothing to choose between. It matches every client the user runs
  these names in, none of which labels an MCP server or a skill twice. Skill's
  `on_rename` hook and `mcp_server`'s eviction-on-rename are deleted, and so is
  the title editor on those pages, so there is less code.
- **Cons.** A user who really wants a different name pays a delete and a
  re-registration, losing the toggles, reach or bindings listed in the refusal.
  A user who wanted a friendlier label writes it into the description instead.
- **Why it wins.** The breakage it prevents lands in files Coffer cannot see and
  cannot repair, while the cost it imposes is visible, named in the refusal,
  and rare.

### Option B — Fix the same names, and give every resource an editable `title` (the design this replaced)

Every resource carries an optional `title` of at most 80 characters, editable
on every kind including the name-fixed ones, synced, and shown in place of the
name when set; agents keep a person-chosen name, title and description.

- **Pros.** The cosmetic reason to rename — "I want it to read better" — is
  served without touching the name. It mirrors the MCP spec's name/title split.
- **Cons.** Two names for one thing: every surface has to pick one, and the one
  it shows is not the one the user types or the agent quotes. For agents, a
  chosen name was what decided which of two agents of a type answered.
- **Why it loses.** The label has no reader outside Coffer, and a description
  already says what the thing is. A second name costs more confusion than the
  cosmetic freedom is worth.

### Option C — Keep every name renamable (the design before names were fixed)

The rename is an ordinary `PATCH` on every kind, as
[A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md)
first decided.

- **Pros.** One rule for every kind; no delete-and-re-add.
- **Cons.** Every permission rule, skill and instruction that quotes the old
  tool names or the old skill name breaks with no signal, and the next session's
  "tool not found" is the first anyone hears of it.
- **Why it loses.** It optimises the rename, which is rare, at the price of
  silent breakage in files outside Coffer.

### Option D — Allow the rename and keep the old prefix as an alias for a deprecation window

The gateway resolves both the old and the new `<server>__` prefix for a period,
the way github-mcp-server keeps old tool names working after renaming tools.

- **Pros.** Nothing breaks on the day of the rename.
- **Cons.** A second resolution path in the gateway, alias bookkeeping that has
  to sync across machines, and the same breakage when the window closes — just
  later, and further from the action that caused it. A skill has no gateway to
  alias through at all: its directory and SKILL.md `name:` would have to exist
  twice.
- **Why it loses.** It postpones the break rather than preventing it.

### Option E — Warn on rename instead of refusing it

- **Pros.** The user keeps the choice.
- **Cons.** The warning is printed once, to the person renaming, while the
  failure lands later in an agent session that never saw it.
- **Why it loses.** A warning printed now protects nobody later.

### Option F — Per-tool renaming in the gateway (`override_name`)

MetaMCP and ToolHive let the operator override individual tool names over a
fixed server name.

- **Pros.** Fine-grained control over what the agent sees.
- **Cons.** A different problem — curating a tool list — and it has the same
  stale-reference hazard for every overridden tool.
- **Why it loses.** Out of scope; the server name stays fixed either way.

### Option G — Rewrite the quoting files on rename

Have Coffer find and rewrite permission rules and skills that cite the old
names.

- **Pros.** A rename that "just works".
- **Cons.** It means Coffer writing into agents' settings files and the user's
  own skills and project instructions by string substitution, which is the
  kind of blind edit [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md)
  exists to prevent, and it can never find every file that quotes a name.
- **Why it loses.** It cannot be complete, and an incomplete rewrite is Option C
  with extra risk.

## Decision

A kind whose resource name is visible outside Coffer declares `name_fixed`,
and its name cannot change after registration: a changed name is refused with
`409 NAME_IMMUTABLE`, naming delete-and-register-again as the only route and
what it resets. Today that is `mcp_server` and `skill`, plus `agent`, whose
name is derived from its type and so cannot change either. The `uid` is still the
identity ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](identity-is-the-uid-inside-the-file.md));
this decision narrows which labels may move, not what identifies a resource.

These three kinds, and `knowledge`, carry no display title: surfaces show the
name, beside an MCP server's description or a skill's `SKILL.md` description.
The optional `title` (at most 80 characters, a key in the resource's own file
so it travels with it, shown in place of the name when set) stays on the kinds
whose name is Coffer's own label: `provider` and `channel`.

A new MCP server's name is capped at 24 characters at registration
(`MCP_SERVER_NAME_MAX_LEN` in `application/mcp/kind.py`): 13 + 24 + 2 leaves 25
of a client's 64 characters for the upstream tool's own name. Names that
already exist, or that arrive from another machine through sync, are kept.
Each discovered capability carries `client_name_length`, the length of
`mcp__coffer__<server>__<tool>`, and the Tools tab and `coffer mcp cap list`
flag any row above 64.

A future kind whose name becomes visible outside Coffer — a path an agent
reads, an identifier it calls — must set `name_fixed` in the same change.

## Consequences

- A rename of an MCP server or a skill is a delete plus an add; there is no
  cosmetic relabel. The web UI shows those two kinds' names as fixed, and the
  MCP JSON import preview names the server name that will be fixed and warns
  above 24 characters before submit.
- Skill's `on_rename` hook and the MCP server's session eviction on rename are
  gone. `knowledge` keeps its `on_rename` hook, which moves its directory ([Kind Plug-in Contract](kind-plugin-contract.md)).
- `coffer mcp add|edit` and `coffer skill add` take no `--title`, and
  `coffer skill edit` does not exist: nothing on a skill's record is editable,
  and its description is changed by editing `SKILL.md`.
- Migration 0109 clears the titles stored on agents, MCP servers and skills,
  and collapses agents to one per type named by it.
- The `title` stays a key of the resource file for the kinds that carry it,
  left out while empty; a file without it leaves the title empty.
- An existing MCP server with a name longer than 24 characters keeps working;
  the only visible effect is the long-tool-name flag on its capabilities.
- Enforced in `application/resource_rename_ops.py` (the refusal), the kinds'
  descriptors (`application/mcp/kind.py`, `application/skill/kind.py`,
  `application/agent/kind.py`, `application/knowledge/kind.py`), the title rule in
  `application/resource_kind_ops.py`, and the resource-framework,
  agent-registry, mcp-gateway and skill-manager specs.
