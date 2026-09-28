## REMOVED Requirements

### Requirement: Show delivery state on the agent's own page
**Reason**: The delivery hook is no longer installed on its own. It is one part of the agent's Coffer connection, whose state — part by part, the hook included — the agent page's header reports (spec agent-registry "Show the Coffer connection on the agent pages"). A separate card on the Memory tab would be a second control over the same entry.
**Migration**: Connect the agent to Coffer from its page header, the Agents list, `coffer agent connect <name>`, or `POST /api/v1/agents/{uid}/coffer-connection`; read the hook's state with `coffer agent connection <name>`. `/api/v1/memory/delivery*` and `coffer memory delivery|delivery-install|delivery-remove` are removed.

## MODIFIED Requirements

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI. Where the agent has a session-start event, delivery MUST use it; where it has none, delivery MUST use its earliest per-session event with a **once-per-session guard**. Installation MUST be an **explicit act** on Coffer's surface — connecting the agent to Coffer, of which the hook is one part (spec agent-registry "Connect an agent to Coffer in one action"), or switching `memory` on while the agent is connected — marker-scoped, removable without disturbing entries Coffer did not write, and idempotent. Coffer MUST NOT install it silently, and MUST NOT write into any file that is an agent's *memory* — a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle event, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker, a second install leaves one entry, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entry — dropping the event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

### Requirement: Audit every delivery fire
Coffer MUST record **an audit event for every delivery fire**, so that whether delivery is actually happening is answerable after the fact. A fire is an event, not a property of the agent: the hook's per-agent status MUST report installation only, and MUST NOT carry a last-fired timestamp.

#### Scenario: every hook fire is recorded in the audit log
- **GIVEN** an agent for which delivery has been installed
- **WHEN** the installed hook fires and the served context is recorded as a delivery
- **THEN** exactly one audit event is written naming that agent as both the resource and the actor
- **AND** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own (see "Audit every delivery fire")

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` and a `coffer memory` CLI group MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, run an aggregation, run a distil pass, compose the session context, and read what has been retired. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family.

#### Scenario: a partition's own directory is browsable as a file tree
- **GIVEN** a distilled partition
- **WHEN** its file tree is requested, and then one file out of it
- **THEN** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **AND** `.raw/` is reachable through the same tree but marked as derived input, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (see "Present partitions as a table and a file tree", "Confine reads to registered agents' memory paths")
