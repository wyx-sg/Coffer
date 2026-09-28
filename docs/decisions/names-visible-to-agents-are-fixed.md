# Names Visible to Agents Are Fixed; Every Resource Carries an Editable Title

**Status**: Accepted
**Date**: 2026-09-28
**Deciders**: Yuxing Wu
**Related**: [Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md), [Kind Plug-in Contract](kind-plugin-contract.md), [Tool Overload: List a Usage-Ranked Slice, Search the Rest](tool-overload-tier-the-list-search-the-rest.md), [Skills Reach an Agent as a Directory Link](cross-platform-skill-delivery.md), research note [MCP gateways](../research/mcp-gateways.md), spec resource-framework "Treat a resource's name as a mutable label", spec resource-framework "Carry an optional editable title on every resource", spec mcp-gateway "Manage MCP servers as resources", spec mcp-gateway "Flag tools whose client-visible name is too long", spec skill-manager "Keep one master folder per skill", OpenSpec change `reshape-cli-and-mcp-surface`

## Context

[Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md)
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

The rename worked inside Coffer — the uid kept the row, the audit trail and the
sync document intact — and broke silently outside it, in files that are the
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

## Options Considered

### Option A — Fix the name of kinds whose name is visible outside Coffer, and give every resource a separate editable `title` (chosen)

`Kind` gains `name_fixed: bool` (`domain/resource.py`). `mcp_server` and
`skill` set it. A `PATCH` whose `name` differs from the current one is refused
with `409 NAME_IMMUTABLE` before any other field of the same request is written
(`application/resource_rename_ops.refuse_fixed_name`). The refusal says the
only way to a new name — delete and register again — and what that resets,
from the kind's `name_fixed_resets`: an MCP server's capability toggles and
reach, a skill's enabled flag, scope and deliveries.

Every resource gains `title`: optional free text of at most 80 characters,
stored in the nullable `resources.title` column, carried in the vault-sync
document, editable on every kind (including the name-fixed ones) with
`coffer <kind> edit --title` and the same `PATCH`. The web UI and the CLI show
the title in place of the name when it is set.

`provider`, `agent`, `channel`, `knowledge` and `memory` keep renamable names,
because their names appear only on Coffer's own surfaces (or, for knowledge and
memory, in a directory Coffer moves itself through the kind's `on_rename` hook).

- **Pros.** Nothing an agent or a user has written down can go stale because of
  Coffer. The cosmetic reason to rename — "I want it to read better" — is
  served by `title` with no cost. It follows the MCP spec's own name/title split
  and matches every client the user runs these names in. Skill's `on_rename`
  hook and `mcp_server`'s eviction-on-rename are deleted, so there is less code.
- **Cons.** A user who really wants a different name pays a delete and a
  re-registration, losing the toggles, reach or bindings listed in the refusal.
- **Why it wins.** The breakage it prevents lands in files Coffer cannot see and
  cannot repair, while the cost it imposes is visible, named in the refusal,
  and rare once `title` exists.

### Option B — Keep every name renamable (the design this replaced)

The rename is an ordinary `PATCH` on every kind, as
[Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md)
first decided.

- **Pros.** One rule for every kind; no delete-and-re-add.
- **Cons.** Every permission rule, skill and instruction that quotes the old
  tool names or the old skill name breaks with no signal, and the next session's
  "tool not found" is the first anyone hears of it.
- **Why it loses.** It optimises the rename, which is rare, at the price of
  silent breakage in files outside Coffer.

### Option C — Allow the rename and keep the old prefix as an alias for a deprecation window

The gateway resolves both the old and the new `<server>__` prefix for a period,
the way github-mcp-server keeps old tool names working after renaming tools.

- **Pros.** Nothing breaks on the day of the rename.
- **Cons.** A second resolution path in the gateway, alias bookkeeping that has
  to sync across machines, and the same breakage when the window closes — just
  later, and further from the action that caused it. A skill has no gateway to
  alias through at all: its directory and SKILL.md `name:` would have to exist
  twice.
- **Why it loses.** It postpones the break rather than preventing it. Worth
  revisiting only if users still ask for renames after `title` has shipped.

### Option D — Warn on rename instead of refusing it

- **Pros.** The user keeps the choice.
- **Cons.** The warning is printed once, to the person renaming, while the
  failure lands later in an agent session that never saw it.
- **Why it loses.** A warning printed now protects nobody later.

### Option E — Per-tool renaming in the gateway (`override_name`)

MetaMCP and ToolHive let the operator override individual tool names over a
fixed server name.

- **Pros.** Fine-grained control over what the agent sees.
- **Cons.** A different problem — curating a tool list — and it has the same
  stale-reference hazard for every overridden tool.
- **Why it loses.** Out of scope; the server name stays fixed either way.

### Option F — Rewrite the quoting files on rename

Have Coffer find and rewrite permission rules and skills that cite the old
names.

- **Pros.** A rename that "just works".
- **Cons.** It means Coffer writing into agents' settings files and the user's
  own skills and project instructions by string substitution, which is the
  kind of blind edit [Writing Agent-Native Config Safely](writing-agent-native-config-safely.md)
  exists to prevent, and it can never find every file that quotes a name.
- **Why it loses.** It cannot be complete, and an incomplete rewrite is Option B
  with extra risk.

## Decision

A kind whose resource name is visible outside Coffer declares `name_fixed`,
and its name cannot change after registration: a changed name is refused with
`409 NAME_IMMUTABLE`, naming delete-and-register-again as the only route and
what it resets. Today that is `mcp_server` and `skill`. The `uid` is still the
identity ([Resource Identity Is an Immutable `uid`](resource-identity-is-an-immutable-uid.md));
this decision narrows which labels may move, not what identifies a resource.

Every resource carries an optional `title` (at most 80 characters) for display,
editable on every kind and synced with the resource. Surfaces show the title
when set and the name otherwise.

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

- A rename of an MCP server or a skill is a delete plus an add; `title` covers
  the cosmetic case. The web UI shows those two kinds' names as fixed, and the
  MCP JSON import preview names the server name that will be fixed and warns
  above 24 characters before submit.
- Skill's `on_rename` hook and the MCP server's session eviction on rename are
  gone. `knowledge` and `memory` keep their `on_rename` hook, which moves their
  directory ([Kind Plug-in Contract](kind-plugin-contract.md)).
- `resources.title` is nullable; a sync peer on an older build ignores the key
  and a document without it leaves the title empty.
- An existing MCP server with a name longer than 24 characters keeps working;
  the only visible effect is the long-tool-name flag on its capabilities.
- Enforced in `application/resource_rename_ops.py` (the refusal), the kinds'
  descriptors (`application/mcp/kind.py`, `application/skill/kind.py`) and the
  resource-framework, mcp-gateway and skill-manager specs.
