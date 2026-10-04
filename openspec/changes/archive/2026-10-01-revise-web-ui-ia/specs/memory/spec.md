## RENAMED Requirements

- FROM: `### Requirement: Present partitions as a table and a file tree`
- TO: `### Requirement: Present a partition as its memories`

## MODIFIED Requirements

### Requirement: Present a partition as its memories
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows — listing the connected agents whose memory Coffer found on this machine, or, with no agent connected, saying there is nothing to read and offering to connect one. Each row MUST carry the partition's path ("Every project" for `global`), a sample memory — or, before a first distil, how many entries were read from which agents and are waiting to distil — how many memories it holds, its sources (the agents it came from, "All agents" when every agent that contributed anywhere contributed here) and its distil state: when it was last distilled, "Not distilled yet", "Distilling…" while a pass over it runs, or "Repository missing" with a Delete action. A partition's page header MUST name its path, its memory count and when it was last distilled, and each memory in its list MUST name the agents it was learned from ("All agents" when that is every agent the partition came from). One partition's page MUST carry two tabs. **Memories** (the default) lists its memories — the web UI's label for what this spec and the disk call notes (中文 记忆条目) — beside the selected memory, with the partition's retired memories in a collapsed, read-only **Retired** group, each with the reason it was retired. The selected memory MUST be rendered with a meta line naming the agents it was learned from and when it was last updated, taken from its provenance ("Record provenance and merge by meaning"), and its frontmatter MUST be shown as that metadata, not rendered as body text. The page MUST NOT show the agents' own memory: no native paths, no original agent text, no `.raw/` entry, no `MEMORY.md` index or `RETIRED.md` file, and no file tree — those stay in the data, on the REST routes and in the CLI (see "Cover memory management on REST and the CLI"), and only this page leaves them out. It MUST offer open-in-editor and reveal-in-file-manager on the selected memory's own file. The list and the memory MUST extend to the bottom of the window and scroll inside. It MUST NOT carry per-memory actions: a memory is derived by distillation, and the page says so by offering none. **Delivered** (`/memory/<uid>/delivered`) shows, read-only, the exact session-start text each agent receives in the partition's project, with a switch between agents ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"); it shows no hook state.

#### Scenario: browse a partition as a file tree with a read-only preview
- **GIVEN** the memory pages, with no partitions and then with one distilled partition that holds raw entries, a memory learned from Claude Code and Codex, and one retired memory
- **WHEN** the partitions page and the partition's page render and the memory is chosen
- **THEN** the partitions page shows the first-run welcome with none and the table with one, and the partition's page lists its memories beside the chosen one, whose meta line names Claude Code and Codex and when it was updated and whose frontmatter is not in the rendered body
- **AND** the retired memory is in a collapsed Retired group with its reason, the page shows no file tree, no `MEMORY.md`, `RETIRED.md` or `.raw/`, no native path and no agent's original text, and it offers open-in-editor and reveal-in-file-manager and no per-memory edit or delete action

#### Scenario: provenance paths stay in the data, not on the page
- **GIVEN** a memory whose provenance names a Claude Code fact file by its native path
- **WHEN** the memory is read over the REST note route and shown on the partition's page
- **THEN** the route's provenance still carries the agent, the native path and the read time, while the page shows only the agent's name and the update time

#### Scenario: a partition has a memories tab and a delivered tab
- **GIVEN** a partition with memories and two connected agents
- **WHEN** the user opens the partition and then its Delivered tab
- **THEN** the page opens on Memories, and Delivered shows each agent's session-start text read-only with an agent switch and no hook state

#### Scenario: the partitions table names each partition's sample, sources and distil state
- **GIVEN** a distilled partition learned from every agent, a partition holding entries read from Codex that no pass has distilled, and a partition whose repository is gone
- **WHEN** the partitions page renders
- **THEN** the first row shows a sample memory, "All agents" and when it was distilled, the second says its entries from Codex are waiting and reads "Not distilled yet", and the third reads "Repository missing" with Delete
