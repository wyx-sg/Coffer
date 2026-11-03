# Memory

## Purpose

Every agent the developer runs keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex consolidates its rollouts into a summary and topic files. Both work well and neither leaves its own directory, so the developer re-teaches each agent what the other already knows, and re-teaches it again on the next machine. Coffer **syncs those memories into each other**: it reads what every registered agent wrote for itself, keeps one copy of each memory in a **hub** in the vault, and writes the hub back into **each agent's own native memory**, where that agent already looks for it.

```
~/.coffer/vault/memory/
├── global/                  ← memories about the person, for every project
└── projects/<project key>/  ← one folder per repository, the same key on every machine
```

**The hub is vault content.** Vault sync carries it to the person's other machines, so a memory one agent learned on one machine reaches every agent on every machine. A project is named by its repository's normalised `origin`, and the paths in a memory are stored portably, so a memory written in one checkout reads true in another.

**Each agent reads the copies the way it reads its own memory.** For Claude Code that is text it loads by itself: the memories of a project in a marked block of that project's `MEMORY.md`, and the global ones in a rules file; Claude Code opens a memory's own file only when its model chooses to, which in practice it does not, so Coffer writes no file per memory there. For Codex it is a memory extension folder, which Codex's consolidation absorbs. Coffer delivers nothing into a session itself: no hook, no index at session start, no retrieval at prompt time.

**Coffer does the mechanical work and nothing else.** It publishes, writes and removes copies; it never merges, rewords or judges a memory, and it never touches a memory an agent wrote. Judgement stays with each agent's own curation (Codex consolidation, Claude Code's Auto Dream), which now sees the other agents' memories beside its own; a copy the agent edited or removed is the agent's, and is not written again. **Curate now** asks an agent to run its curation at once.

**Memory is about the person; knowledge is about the world.** Memory holds who the person is, how to work with them, and a project's current state. [Knowledge](../knowledge/spec.md) holds how outside systems, teams and processes work: what needs a source, goes stale or is worth sharing. A fixed sequence of steps is a [skill](../skill-manager/spec.md). Agents still write task notes into their own memory, so Coffer flags the memories an agent filed as task material, keeps them with that agent, and on request hands them to the person's agent to sort into knowledge, a skill, memory or nothing.

| | Memory | Knowledge |
| --- | --- | --- |
| Holds | the person, how to work with them, a project's state | outside systems, teams, processes, their pitfalls |
| Where it comes from | agents' native memories | the human uploads it, or writes it with an agent; task notes sorted out of memory |
| Partitioned by | project (and `global`) | collection |
| Who authors the stored text | the agent that learned it; Coffer copies it as it stands | the human or an agent, directly |
| Reaches an agent by | **push**: text or a copy in the agent's own memory | **pull**: the agent reaches for it |
| Tidied by | each agent's own curation | an agent on request (Tidy) |

The first sync on a machine, and any sync that would change more than 50 copies, waits as a **preview** the person writes or cancels, and **Undo sync** removes every copy Coffer wrote that the agent has not edited. The page and the `coffer memory` commands manage the sync; neither reads or writes a memory's text.

While the `memory` feature is switched off (spec [experimental-features](../experimental-features/spec.md)), the memory routes are closed and the memory sync skips its rounds; the copies already written stay in the agents' own memory.

## Requirements

### Requirement: Read no transcripts or rollouts
A sync MUST NOT read session transcripts, rollouts or raw capture files **as a source of entries**. Both supported agents already distil their own; this layer starts from that output. The single narrow exception is Claude Code's project slug, which encodes a path lossily: the reader MAY scan a project's own session transcripts for the `cwd` they recorded, accepting it only when Claude Code's encoding of that `cwd` is exactly the slug, so that a renamed or deleted project still files under its real repository. Codex's v2 memory files its topics under named scopes and records each one's directory only in the header of the rollout summary the topic points at: the reader MAY read that header's `cwd:` line and nothing below it. Nothing but those recorded paths is taken, and no transcript or rollout summary is ever listed as a source.

#### Scenario: list no transcript or rollout as a source
- **GIVEN** a Claude Code config directory holding a session transcript beside a project's memory directory, and a Codex home holding session rollouts beside its memory files
- **WHEN** each reader lists its sources
- **THEN** no transcript, rollout or raw capture file is among them

### Requirement: Read Claude Code and Codex memory with their search terms
v1 MUST support two readers. **Claude Code**: per-fact Markdown files under its per-project memory directories, whose frontmatter carries the entry's name, description and type. **Codex**: its `MEMORY.md` task groups — each group's applicability, preferences, reusable knowledge and failures — and its distilled profile summary. Where the source states **search terms** for an entry, as Codex's summary does for each task group, the reader MUST carry them onto the raw entry and the hub entry: they are the source's own answer to "what would you look this up by". Each reader MUST ignore the agent's own index or roll-up file, which only restates the entries.

#### Scenario: a Claude Code memory file becomes a raw entry
- **GIVEN** a Claude Code per-project memory directory holding one fact file whose frontmatter carries `name`, `description` and `type`
- **WHEN** the Claude Code reader lists its sources and reads that one
- **THEN** exactly one raw entry comes back: its title is the `name`, its description the `description`, its type `feedback`, its body the prose with the frontmatter fence stripped out, its anchor the file's own stem, and its project root the project that memory directory belongs to
- **AND** the agent's own roll-up file (`MEMORY.md`) is not among the sources at all

#### Scenario: a Codex task group becomes raw entries carrying its own search terms
- **GIVEN** Codex's `MEMORY.md` holding two task groups, one of which records the working directory it was learned in, and a `memory_summary.md` whose `What's in Memory` section lists those groups with their search terms
- **WHEN** the Codex reader reads both files
- **THEN** one raw entry comes back per populated bullet section of each group, each carrying that group's recorded cwd as its project root
- **AND** each entry carries the **search terms** its group's summary entry lists
- **AND** the group's own rollout-reference subsections never surface as entries

### Requirement: Fail a broken reader loudly and in isolation
A reader that cannot parse its source — the agent changed its format — MUST fail **loudly and in isolation**: that agent contributes nothing to the hub in that sync, the Memory page says so with the path and the reason, the other agent's memory is still read, and hub entries it published earlier are left standing rather than deleted. A writer that does not recognise the layout it is about to write into (Claude Code's memory directory, or Codex's memory folder without the extension layout Coffer expects) MUST write nothing for that agent and report it the same way.

#### Scenario: an agent whose native memory shape is unreadable degrades loudly
- **GIVEN** one agent holding a memory file whose frontmatter is missing, unterminated, not a mapping, or missing its name field, and a second agent whose memory is fine
- **WHEN** memory syncs
- **THEN** the sync reports one failure naming the agent, the path and the reason
- **AND** the other agent's memories are published as normal, and the first agent's earlier hub entries are left standing

#### Scenario: an unrecognised layout is not written into
- **GIVEN** a Codex memory folder whose layout Coffer does not recognise
- **WHEN** memory syncs
- **THEN** nothing is written under it and the Memory page names the path and the reason

### Requirement: Skip unchanged sources
A sync MUST skip a source file whose content hash is unchanged since the last sync, and MUST record enough per source to make that decision without re-parsing.

#### Scenario: an unchanged source file is skipped on the next sync
- **GIVEN** a source already read by one sync, whose content hash has not changed since
- **WHEN** a second sync runs
- **THEN** the source is counted as skipped and is **not read at all** — a reader rigged to raise if consulted again is never consulted
- **AND** no failure is reported and the hub entries that source produced stay

### Requirement: Show memory events on the vault-wide audit surface
This layer MUST NOT carry an audit surface of its own. Its events are read on the vault-wide audit surface, and every event type this layer records MUST be legible there rather than shown as a raw event code.

#### Scenario: label every memory event type on the audit surface
- **GIVEN** every audit event type the memory layer records
- **WHEN** each is rendered by the vault-wide audit surface's event labelling
- **THEN** each has a human-readable label in both interface languages rather than its raw event code

### Requirement: Confine reads to registered agents' memory paths
Reading and writing MUST be confined to the memory paths of registered agents' config directories and to `vault/memory/`. Every path built from a source's contents or a hub entry MUST pass a traversal guard.

#### Scenario: refuse a path segment built from source contents that escapes
- **GIVEN** a project key, slug or source identity taken from a source's or hub entry's contents that is `..`, contains a path separator, or is hidden
- **WHEN** a path under the hub or an agent's memory directory is built from it
- **THEN** it is refused with `UnsafeMemoryPath` rather than resolved outside it

### Requirement: Read only registered agents' memory
Coffer MUST read the native memory of each **registered** agent, from a path derived from that agent's own `config_dir` ([agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.

#### Scenario: read nothing from an unregistered agent
- **GIVEN** fixture memory for a registered agent and in a config directory no registered agent names
- **WHEN** memory syncs
- **THEN** hub entries come only from the registered agent's memory
- **AND** nothing is read from the unregistered directory

### Requirement: Keep every agent's memories in a hub in the vault
Coffer MUST keep every memory that a registered agent on any of the person's machines wrote for itself as one Markdown file in the vault, under `vault/memory/global/` or `vault/memory/projects/<project>/`. Each file MUST carry frontmatter naming its origin (machine id, agent type and the source's own identity), its `type` (`user`, `feedback`, `project` or `reference`), its `title`, a one-line `description`, `created_at` and `updated_at`, and the memory's text as its body. A memory MUST be filed where its agent filed it, whatever its type: one learned in a repository under that repository's project, and one with no working directory (Codex's profile, a Codex task group that names none) under `global`. The hub is vault content, so vault sync carries it to the person's other machines like any other vault file ([vault-sync](../vault-sync/spec.md)).

#### Scenario: an agent's memory becomes one hub file
- **GIVEN** a registered Claude Code with one `feedback` memory file in the memory directory of a checkout of `github.com/acme/payments`
- **WHEN** memory syncs
- **THEN** exactly one file appears under `vault/memory/projects/github.com-acme-payments/`, whose frontmatter names this machine, `claude_code`, the source file, the type `feedback`, its title and description, and whose body is the memory's text
- **AND** the change is one vault commit naming the memory sync as its writer

#### Scenario: a memory about the person is filed under global
- **GIVEN** a Claude Code memory typed `user` learned in a directory inside no repository, a Claude Code memory typed `user` learned in a checkout of `github.com/acme/payments`, and a Codex profile entry
- **WHEN** memory syncs
- **THEN** the first and the profile entry are filed under `vault/memory/global/`
- **AND** the memory learned in the checkout is filed under that project

#### Scenario: a Codex preference follows the repository its task worked in
- **GIVEN** a Codex task group whose `applies_to` names a scratch chat directory and, beside it, a checkout of `github.com/acme/payments`, with a `User preferences` bullet; and a task group that names only the scratch directory
- **WHEN** memory syncs
- **THEN** the first group's preference is filed under `github.com-acme-payments`
- **AND** the second group's preference is filed under `global`

#### Scenario: the hub travels with vault sync
- **GIVEN** two machines syncing one vault, and a hub entry published on the first
- **WHEN** a sync round completes on the second
- **THEN** the second machine holds the same hub file

### Requirement: Identify a project by a key that does not depend on the machine
A project in the hub MUST be named by its repository's `origin` URL, normalised (scheme, credentials and a trailing `.git` dropped, lower-cased host), and by the repository directory's name when it has no `origin`. A main checkout, its worktrees and another clone with the same `origin` MUST resolve to one project, on one machine or across machines. A memory whose agent names several working directories MUST be filed under the first of them inside a repository. A memory learned only in directories that are not inside a repository MUST be filed under `global` when its type is `user`, and otherwise MUST NOT be published.

#### Scenario: two clones on two machines share one project
- **GIVEN** a checkout of `git@github.com:acme/payments.git` at `/Users/a/src/payments` on one machine and of `https://github.com/acme/payments` at `/home/b/work/pay` on another
- **WHEN** each machine publishes a memory learned in its checkout
- **THEN** both land under one project, `github.com-acme-payments`

#### Scenario: a memory from a scratch directory is not published
- **GIVEN** a `project` memory learned in a directory that is not inside a repository
- **WHEN** memory syncs
- **THEN** no hub file is written for it

### Requirement: Store paths in a memory portably
When a memory is published, every occurrence of its repository's local root in its text MUST be replaced by `<repo>` and every occurrence of the person's home directory by `~`. When a hub entry is written into an agent, `<repo>` MUST be expanded to that project's checkout on the writing machine and `~` to that machine's home directory. Any other path MUST be left as written.

#### Scenario: a path follows the repository to another machine
- **GIVEN** a memory published from a checkout at `/Users/a/src/payments` whose text names `/Users/a/src/payments/ledger/retry.py` and `/Users/a/.config/tool.toml`
- **WHEN** it is written on a machine where the project is checked out at `/home/b/work/pay` and the home directory is `/home/b`
- **THEN** the copy names `/home/b/work/pay/ledger/retry.py` and `/home/b/.config/tool.toml`
- **AND** the hub file names `<repo>/ledger/retry.py` and `~/.config/tool.toml`

### Requirement: Publish only what the origin agent wrote, and only from its machine
Each sync MUST read the registered agents' native memory, create or update the hub entry for each memory the agent wrote itself, and delete the hub entry of a memory the agent no longer holds. Only the machine and agent a hub entry came from MUST change or delete it; a machine MUST NOT delete another machine's entry because its own agents lack that memory.

#### Scenario: a memory the agent changed updates its hub entry
- **GIVEN** a published Codex memory whose bullet Codex rewrote
- **WHEN** memory syncs on the same machine
- **THEN** the hub entry's body and `updated_at` change and no new hub entry is created

#### Scenario: a memory the agent dropped leaves the hub
- **GIVEN** a published Claude Code memory whose file the person deleted
- **WHEN** memory syncs on the same machine
- **THEN** its hub entry is deleted

#### Scenario: another machine's entry is left alone
- **GIVEN** a hub entry published by another machine, and no agent on this machine holding that memory
- **WHEN** memory syncs on this machine
- **THEN** the hub entry is unchanged

### Requirement: Withhold a memory that looks like a secret
A memory whose text holds something shaped like a secret (an API key, a token, a private key or a password assignment, by the same shapes the secret boundary detects) MUST NOT be published to the hub. The sync report MUST name the agent and source it withheld, never the matched text.

#### Scenario: a memory holding a token is withheld
- **GIVEN** a Claude Code memory whose body contains an `sk-` API key
- **WHEN** memory syncs
- **THEN** no hub entry is written for it, and the sync's Activity entry lists it as withheld by agent and source path only

### Requirement: Write the hub into Claude Code as text it loads
Coffer MUST write each hub entry that did not come from this machine's Claude Code into Claude Code as text Claude Code loads by itself, and MUST NOT write a file per memory. A project's entries MUST go, for each project checked out on this machine, into a marked block at the end of that project's `MEMORY.md` (in `<config_dir>/projects/<project>/memory/`, created when missing, named the way Claude Code names it for the repository's root), between `<!-- coffer:memory-sync:begin -->` and `<!-- coffer:memory-sync:end -->`, so they load only in sessions in that project. `global` entries MUST go into `<config_dir>/rules/coffer-memory.md`, a file Coffer owns entirely, which Claude Code loads in every session and which says at its top that Coffer writes it. Each memory MUST be one line holding its text (its title in front when the text does not open with it, at most 800 characters) and the agent it came from; Codex's User Profile MUST come first, then the newest memory first. The block MUST stay within 4 KB and the rules file within 8 KB; memories that do not fit MUST be counted in a last line naming the `coffer memory entries` command that lists them. Coffer MUST back `MEMORY.md` up before changing it and MUST NOT change anything in it outside the marked block. Copies an earlier build wrote as `coffer_` files, and its `-coffer-global` project, are no longer targets, so the next sync removes the ones still as written and empties their blocks.

#### Scenario: a project's memories reach only that project
- **GIVEN** a hub entry from Codex for `github.com-acme-payments`, sorted back into memory, that repository checked out with Claude Code registered, and another checked-out project
- **WHEN** memory syncs
- **THEN** the marked block of the payments project's `MEMORY.md` holds the memory's text, and the other project's `MEMORY.md` and the rules file do not
- **AND** every line of `MEMORY.md` outside the block is byte-identical to before, a backup of the previous `MEMORY.md` exists, and no `coffer_` file is written

#### Scenario: the marked block is bounded
- **GIVEN** 45 memories of 250 characters for one project
- **WHEN** the marked block is rendered
- **THEN** it holds the newest of them within 4 KB, then one line counting the rest and naming `coffer memory entries --project github.com/acme/payments`

#### Scenario: a Codex profile reaches every Claude Code session
- **GIVEN** a `global` hub entry from Codex stating the person's preferred language
- **WHEN** memory syncs
- **THEN** `<config_dir>/rules/coffer-memory.md` holds that entry's text
- **AND** no project's `MEMORY.md` is changed for it, and no `-coffer-global` project is made

#### Scenario: the rules file stays bounded
- **GIVEN** 40 `global` hub entries of 400 characters
- **WHEN** the rules file is rendered
- **THEN** it is at most 8 KB, holds the newest of them, and counts the rest in a line naming `coffer memory entries --project global`

### Requirement: Flag the memories an agent filed as task material
Coffer MUST flag a hub entry as **task material** from where its agent filed it, judging no text: a Codex memory whose identity names a task group (a bullet of a `MEMORY.md` task group, or a project's item of the newer summary's "What's in Memory"), and a Claude Code memory typed `reference`. Codex's profile, preferences and general tips and Claude Code's `user`, `feedback` and `project` memories MUST NOT be flagged.

#### Scenario: task material is flagged from where it was filed
- **GIVEN** a Codex task-group bullet, Codex's User Profile and one of its preferences, and Claude Code memories typed `reference`, `user`, `feedback` and `project`
- **WHEN** each is checked
- **THEN** only the task-group bullet and the `reference` memory are task material

### Requirement: Keep task material with its own agent until it is sorted
A hub entry flagged as task material MUST NOT be written into an agent of another type until it is sorted back into memory; it MUST still be written into its own agent type on the person's other machines. A copy of it already written into another agent MUST be removed by the next sync, as any copy that is no longer a target. The Memory page MUST show such a copy's state as staying with its own agent.

#### Scenario: task material stays with its own agent until it is sorted
- **GIVEN** a Codex task-group bullet and a Claude Code `reference` memory for a project checked out with both agents
- **WHEN** memory syncs
- **THEN** neither is written into the other agent, and the page counts two memories to sort
- **AND** once the Codex one is recorded as sorted into memory and the Claude Code one into knowledge, the next sync writes the Codex one into Claude Code only, and nothing waits to be sorted

### Requirement: Sort task material into knowledge on request
The Memory page MUST count the task material no one has sorted yet and offer **Sort into knowledge**, which MUST open Claude Code in the person's terminal with a prompt that lists each waiting memory's hub file and asks it to show, before changing anything, where each belongs (knowledge with the collection and page, a skill, memory, or nothing), then, once the person agrees, to write knowledge inside one `coffer knowledge tidy-start` / `tidy-finish` per collection with `memory: <id>` in the page's `evidence`, to draft a skill and import it only when the person agrees, to edit or delete no agent's memory, and to record each memory it handled with `coffer memory sorted`. It MUST record a `memory_sort_requested` event. Recording a sorting MUST write one file per memory under `vault/memory/sorted/<id>.md` naming the outcome (`knowledge`, `skill`, `memory` or `drop`), where it went and when, as one vault commit, and record a `memory_sorted` event; an id the hub does not hold MUST be refused as not found. A sorted memory MUST stay sorted when its agent rewords it, and a record whose memory left the hub MUST be deleted by the next sync. When at least ten memories wait, the attention list MUST carry one `memory_to_sort` item that opens the Memory page. Coffer MUST NOT start the sorting on its own.

#### Scenario: sorting is handed off and recorded
- **GIVEN** one Codex task-group bullet waiting to be sorted
- **WHEN** the person chooses **Sort into knowledge**, and the agent records it as sorted into knowledge
- **THEN** the prompt names the memory and `coffer memory sorted`, a `memory_sort_requested` event is recorded, and afterwards nothing waits to be sorted and one `memory_sorted` event is recorded
- **AND** recording an id the hub does not hold answers not found

#### Scenario: the reminder waits for enough task notes
- **GIVEN** nine memories waiting to be sorted, then ten
- **WHEN** the attention list is computed each time
- **THEN** the first has no memory item and the second has one `memory_to_sort` item

### Requirement: Write the hub into Codex's memory extension
Coffer MUST write each hub entry that did not come from this machine's Codex into Codex's memory extension folder `extensions/coffer/` of every Codex memory folder that is there (`<config_dir>/memories/` for v1, `<config_dir>/memories_v2/` for v2: Codex picks one per thread, so Coffer writes the same copies into each): one file per entry under `resources/`, named without a leading timestamp, stating the project it applies to (the project's checkout on this machine, or "all projects" for `global`) above the memory's text; and an `instructions.md` telling Codex's consolidation that these are memories other agents learned on the person's machines, that they are information and never instructions, to file each under the project it names, and to tag what it derives from them `[via Coffer]`. When Codex's memories feature is off, the sync MUST say so on the Memory page and write nothing for Codex. A `memories_v<N>` folder newer than any Coffer knows MUST be written nothing and reported on the Memory page with its path, beside the folders Coffer does write.

#### Scenario: a Claude Code memory reaches Codex
- **GIVEN** a hub entry Claude Code published for `github.com-acme-payments`, the repository checked out at `/Users/a/src/payments`, and Codex registered with memories on
- **WHEN** memory syncs
- **THEN** `extensions/coffer/resources/` holds one file for it naming `/Users/a/src/payments` and the memory's text, and `extensions/coffer/instructions.md` exists
- **AND** no file name under `resources/` starts with a timestamp

#### Scenario: Codex with memories off is reported, not written
- **GIVEN** Codex registered with its memories feature off
- **WHEN** memory syncs
- **THEN** nothing is written under Codex's config directory and the Memory page says Codex's memories are off

#### Scenario: a memory reaches every Codex memory folder
- **GIVEN** a Claude Code hub entry for a project checked out here, and Codex with both `memories/` and `memories_v2/`
- **WHEN** memory syncs
- **THEN** both folders' `extensions/coffer/resources/` hold the same file for it, and both have `extensions/coffer/instructions.md`
- **AND** the Memory page lists each folder with the copies written into it

#### Scenario: a newer Codex memory folder is reported, not written
- **GIVEN** Codex with `memories/`, `memories_v2/` and a `memories_v3/` Coffer does not know
- **WHEN** memory syncs
- **THEN** `memories/` and `memories_v2/` are written into, nothing is written under `memories_v3/`, and the Memory page names `memories_v3/` as a folder Coffer cannot write into yet

### Requirement: Write a project's memories only where it is checked out
A machine MUST write a project's hub entries into its agents only when the project is checked out on that machine, as found from the working directories its registered agents recorded; until then the entries MUST stay in the hub unwritten. `global` entries MUST be written on every machine.

#### Scenario: a project not checked out here is held back
- **GIVEN** hub entries for a project no registered agent on this machine has worked in
- **WHEN** memory syncs
- **THEN** none of them is written into any agent here
- **AND** once a registered agent records a working directory in that project, the next sync writes them

### Requirement: Never write a memory back into the agent and machine it came from
A hub entry MUST NOT be written into the agent it came from on the machine it came from. It MUST be written into that same agent type on the person's other machines.

#### Scenario: a memory returns to its own agent on another machine only
- **GIVEN** a hub entry published by Claude Code on machine A
- **WHEN** memory syncs on machine A and on machine B
- **THEN** machine A writes it into Codex only, and machine B writes it into both Claude Code (the project's marked block) and Codex

### Requirement: Never republish Coffer's own copies
A copy Coffer wrote MUST be recognised when its agent's memory is read back and MUST NOT become a hub entry: on Claude Code the marked block, the rules file, and a `coffer_` file with a `coffer:` block left by an earlier build; on Codex by the extension folder and by the `[via Coffer]` tag on content Codex derived from it (a tagged bullet is skipped whole; in the prose of the user profile, the tagged sentence is dropped and the rest read). When an agent's own memory changes only by text already covered by copies Coffer delivered to that agent, Coffer MUST record the new text against the hub entry without publishing a change, so an agent's rewording of what it absorbed does not circulate.

#### Scenario: a copy read back is not published
- **GIVEN** a `coffer_` copy an earlier Coffer wrote into Claude Code, and a Codex `MEMORY.md` bullet tagged `[via Coffer]`
- **WHEN** memory syncs
- **THEN** neither produces a hub entry

#### Scenario: an absorbed copy does not circulate
- **GIVEN** Claude Code's own memory gained, in one of its own files, only a sentence Coffer had written into its rules file from a Codex hub entry
- **WHEN** memory syncs
- **THEN** no hub entry is created or changed for that addition

### Requirement: Leave every memory an agent wrote untouched
Coffer MUST NOT create, change, move or delete any file in an agent's memory other than its own copies, the marked block in Claude Code's `MEMORY.md`, its rules file and its Codex extension folder, and MUST NOT change an agent's memory settings. Merging, correcting and forgetting are the agent's own curation.

#### Scenario: an agent's own files are byte-identical after a sync
- **GIVEN** both agents' memory directories snapshotted with their modification times, and hub entries to write into each
- **WHEN** memory syncs
- **THEN** every file the agent wrote itself is byte-identical with an unchanged modification time, and the only differences are Coffer's own copies, the marked block, the rules file and the extension folder

### Requirement: Hand an edited or removed copy to the agent
A copy whose content no longer matches what Coffer last wrote MUST NOT be overwritten, and a copy the agent removed MUST NOT be recreated, for as long as its hub entry is unchanged. When the hub entry changes, Coffer MUST write the new version as a new copy rather than over the agent's edit. Removing a copy MUST NOT delete its hub entry.

#### Scenario: a copy Auto Dream merged away is not brought back
- **GIVEN** a copy in Codex's extension folder that Codex's own curation absorbed and deleted
- **WHEN** memory syncs and the hub entry has not changed
- **THEN** the copy is not recreated and the hub entry stays

#### Scenario: a copy the agent edited is not overwritten
- **GIVEN** a copy in Codex's extension folder whose body the agent edited
- **WHEN** memory syncs
- **THEN** the file keeps the agent's edit

### Requirement: Defer to Codex's own import from Claude Code
When Codex's own import from Claude Code is on with automatic updates on this machine, Coffer MUST NOT write Claude Code's memories into Codex on that machine, and Codex's Memory tab MUST say that Codex imports them itself. The other direction MUST continue.

#### Scenario: Codex's own import turns the Claude Code to Codex direction off
- **GIVEN** Codex's import from Claude Code on with automatic updates, and a hub entry from Claude Code
- **WHEN** memory syncs
- **THEN** no resource is written for it in Codex's extension folder, and Codex's Memory tab says Codex imports Claude Code's memories itself

### Requirement: Preview a first or large sync
The first sync on a machine, and any sync that would write more copies than a threshold (50 by default), MUST NOT write into any agent until the person confirms it on the Memory page, which lists per agent and project how many copies would be written, updated and removed, folded to those counts until opened (a group that removes anything starts open), and opened lists each memory with what the sync would do to its copy; a memory it would write or update opens in the memory drawer. Publishing to the hub MUST proceed without waiting.

#### Scenario: the first sync waits for the person
- **GIVEN** a machine that has never synced memory, with memories to write into both agents
- **WHEN** memory syncs
- **THEN** the hub is updated, nothing is written into either agent, and the Memory page counts the preview among what needs the person; its drawer lists each agent and project with its counts and, opened, each memory, with **Write** and **Cancel**
- **AND** choosing **Write** writes exactly what the preview listed

### Requirement: Sync on an interval and on demand
Memory sync MUST run on a background worker at daemon start and then on an interval (one hour by default), and MUST be runnable by hand with **Sync now** on the Memory page. Its switch and interval MUST be settable and read per pass ([internal-engine](../internal-engine/spec.md) "Apply a changed switch or interval without a restart"). Only one sync MUST run at a time; a request while one runs MUST be answered as already running. A sync MUST skip a source whose content hash is unchanged (see "Skip unchanged sources").

#### Scenario: a sync runs at start and on demand
- **GIVEN** the memory sync worker configured with an interval
- **WHEN** the daemon starts, and later the person chooses **Sync now** while no sync runs
- **THEN** one sync runs at start under the worker's actor and one under the person's
- **AND** choosing **Sync now** again while it runs reports that a sync is already running

### Requirement: Record every sync in Activity
Every sync that changed anything MUST record one `memory_synced` audit event with its actor, listing the hub entries published, updated and deleted, the copies written, updated and removed per agent and file path, the memories withheld, and every source it could not read. A sync that changed nothing MUST NOT record an event.

#### Scenario: a sync lists what it wrote
- **GIVEN** a sync that publishes one memory and writes two copies
- **WHEN** it finishes
- **THEN** one `memory_synced` event lists the hub entry and both copy paths, and Activity renders it

### Requirement: Undo sync
**Undo sync…** on the Memory page MUST, after a confirmation naming what it removes, delete every copy Coffer wrote on this machine that the agent has not changed, the marked block from each `MEMORY.md`, the Claude Code rules file and the Codex extension folder, turn automatic sync off, and record a `memory_sync_undone` event. It MUST NOT delete hub entries or anything an agent wrote itself.

#### Scenario: undo removes Coffer's copies and nothing else
- **GIVEN** two copies written into Codex, one of which Codex edited, and a rules file written into Claude Code
- **WHEN** the person confirms **Undo sync…**
- **THEN** the unedited copy, the marked blocks and the rules file are gone, the edited copy remains, the agent's own files and the hub are unchanged and automatic sync is off

### Requirement: Show each agent's own curation and ask it to curate now
Each registered agent's Memory tab MUST show, while the memory feature is on, whether the agent's own memory and its own curation are on (Claude Code's auto memory and Auto Dream; Codex's memories feature), with a hint to turn either on when it is off, and the copies Coffer wrote into it on this machine (and how many the agent has since edited or removed), or why Coffer cannot write into it. For Claude Code it MUST say whether Auto Dream's state comes from `autoDreamEnabled` in `settings.json` or from the account default Claude Code caches, and when Auto Dream last ran on this machine. While Auto Dream is off, **Turn on** MUST, only after the person confirms, add `"autoDreamEnabled": true` to Claude Code's `settings.json` with a backup of the file and nothing else in it changed, and record a `memory_curation_enabled` event; Coffer MUST NOT change that setting unasked. The Memory page MUST NOT list the agents; it MUST count an agent Coffer cannot write into among what needs the person, linking to that agent's Memory tab. **Curate now**, offered on Claude Code only, MUST open Claude Code in the person's terminal with a prompt that lists the memory folders Coffer wrote into on this machine and asks it to consolidate them the way Auto Dream would, leaving Coffer's block and rules file as they are, and MUST record a `memory_curation_requested` event; Codex MUST NOT offer it, since its consolidation runs on its own.

#### Scenario: an agent's curation state is shown
- **GIVEN** Claude Code with auto memory on and Auto Dream off, and Codex with memories on
- **WHEN** the person opens each agent's Memory tab
- **THEN** Claude Code's says auto memory is on and Auto Dream is off with a hint to turn it on, and Codex's says its memories are on
- **AND** the Memory page shows no row or chip per agent

#### Scenario: the person turns Claude Code's Auto Dream on
- **GIVEN** Claude Code with auto memory on and Auto Dream off by its account default
- **WHEN** the person chooses **Turn on** on its Memory tab and confirms
- **THEN** Coffer adds `"autoDreamEnabled": true` to its `settings.json`, keeping a backup and the rest of the file unchanged
- **AND** records a `memory_curation_enabled` event

#### Scenario: Curate now opens Claude Code in a terminal
- **GIVEN** Claude Code holding Coffer's blocks in two project memory folders
- **WHEN** the person chooses **Curate now** on its Memory tab
- **THEN** Claude Code opens in the person's terminal with a prompt naming both folders
- **AND** a `memory_curation_requested` event is recorded, and Codex's tab offers no **Curate now**

### Requirement: Deliver no memory into a session
Coffer MUST NOT put memory into an agent's session itself: no session-start context, no notes added to a prompt, and nothing added to a channel turn's system prompt or message. An agent reaches memory only through its own native memory.

#### Scenario: a channel turn carries no memory from Coffer
- **GIVEN** hub entries for the conversation's project and a channel turn about it
- **WHEN** the turn is composed
- **THEN** its system prompt and the message the agent receives carry nothing from the memory layer

### Requirement: Remove the memory delivery hook on upgrade
On the first start of a build carrying this requirement, Coffer MUST remove its `coffer-memory` hook entries from every agent's settings (leaving every other hook and setting untouched), delete `~/.coffer/derived/memory/` and the derived `memory` resource files, and record one `memory_hook_removed` event per agent it changed.

#### Scenario: an upgrade removes the old hook and derived tree
- **GIVEN** an agent whose settings hold Coffer's two memory hook entries beside one of the person's own hooks, and a derived memory tree
- **WHEN** the upgraded daemon starts
- **THEN** both Coffer entries are gone, the person's hook is unchanged, and `~/.coffer/derived/memory/` no longer exists

### Requirement: Manage memory sync in the web UI and on the command line
The Memory page MUST show the sync switch and interval, **Sync now**, when memory last synced and the next sync, **Undo sync…**, and one banner counting what needs the person — a pending preview, each source the last sync could not read, each memory it withheld, each agent Coffer cannot write into — whose drawer lists them. Below, it MUST list the hub's scopes — global memories, then the hub's projects by short name with how many memories each holds, the ones not checked out on this machine grouped apart — beside the open scope's memories (`/memory?scope=`), each with its title and description, type, origin agent and machine and last change, filterable by text and origin agent (`?source=`). A memory's copy state MUST show on its row only when it waits for the next sync or the agent's curation edited or removed it. Opening a memory (`&memory=<id>`) MUST show, in the shared drawer, first one line per local agent with its copy's state, the file that holds it and Open / Reveal, then the memory's text, read only. The page MUST NOT offer to edit a memory's text: the person edits memory in the agent's own memory directory. The old addresses `/memory/projects/<folder>` and `/memory/global` MUST open that scope. Every operation of the page MUST also be a `coffer memory` command.

#### Scenario: a project's memories show where each was written
- **GIVEN** a project with two hub entries, one written into Claude Code and one whose copy Claude Code's curation removed
- **WHEN** the person opens the project on the Memory page
- **THEN** each memory shows its origin agent and machine, the first says nothing about its copy and the second reads removed by Claude Code

#### Scenario: a memory opens with its text and where each agent holds it
- **GIVEN** a Claude Code memory written into Codex
- **WHEN** the person opens it
- **THEN** the drawer lists Claude Code with its own file and Codex as written with the copy's file, each with Open and Reveal, above the memory's text
- **AND** an id the hub does not hold answers not found

#### Scenario: memory sync is managed on the command line
- **GIVEN** the `coffer memory` command group
- **WHEN** its commands are listed
- **THEN** they are `state`, `sync`, `preview-write`, `preview-cancel`, `undo`, `codex-import`, `entries`, `show`, `curate`, `curation-enable`, `to-sort`, `sort` and `sorted`, one per operation of the pages, `show` reads one memory's text and none writes it

### Requirement: Audit every sync, undo and curation request
Every sync that changed something, every undo, every curation request, every sort request, every recorded sorting and every hook removal on upgrade MUST record an audit event with its actor. An agent's own change to its memory is not a Coffer act and is not audited.

#### Scenario: audit a requested sync with its actor
- **GIVEN** a registered agent with native memory to publish
- **WHEN** a user chooses **Sync now**
- **THEN** exactly one `memory_synced` event names that user as its actor, beside any the daemon's own worker recorded under its own actor

### Requirement: Add no table or resource kind
This layer MUST add **no table of its own** and no resource kind. The hub and the sorting records are files in the vault; what a machine wrote into its agents is recorded in one machine-local file, `local/memory-sync.json`.

#### Scenario: keep the hub and the ledger as files only
- **GIVEN** a history database upgraded to head
- **WHEN** its tables are listed after a sync that published and wrote memories
- **THEN** no table is named for memory, no resource of kind `memory` exists, and the ledger is `local/memory-sync.json`

### Requirement: Reintroduce no retired memory mechanism
This layer MUST NOT reintroduce transcript distillation, a Coffer-run model over memory, native-memory projection (taking over an agent's memory directory or switching its own memory off), Coffer's own notes, or any delivery of memory into a session. The two readers and two writers are written as two each; a third agent earns an abstraction, not before.

#### Scenario: register exactly the two readers and two writers
- **GIVEN** the memory layer's reader and writer registries
- **WHEN** they are listed
- **THEN** there is exactly one reader and one writer for Claude Code and one each for Codex

### Requirement: Keep a Codex memory's id when its bullet moves or is rewritten
A Codex memory's hub id MUST NOT depend on its bullet's position. Its source identity MUST be its file, task group, section and the bullet's content, so inserting, removing or reordering other bullets leaves it unchanged. A bullet whose content identity is not in the hub MUST take over the identity of the most alike entry that the same source published in the same section and that no current bullet holds, when the two are at least 0.6 alike (`difflib` ratio of their descriptions), so a rewritten bullet stays an update; any other bullet MUST be a new memory.

#### Scenario: a Codex memory keeps its id when bullets around it move
- **GIVEN** a published Codex section with three bullets
- **WHEN** Codex inserts a new bullet first, drops the second and swaps the other two, and memory syncs
- **THEN** the two remaining bullets keep their hub ids, the new bullet is created, the dropped one is deleted, and nothing is reported as updated

#### Scenario: a Codex bullet replaced by an unrelated one is a new memory
- **GIVEN** a published Codex bullet
- **WHEN** Codex replaces it with a bullet about something else, and memory syncs
- **THEN** the old hub entry is deleted and the new bullet gets a new id; nothing is reported as updated

### Requirement: Read Codex's v2 memory
The Codex reader MUST also read Codex's v2 memory, `<config_dir>/memories_v2/memory_summary.md`, beside v1. v2 has no `MEMORY.md`; from its summary the reader takes the User Profile, each User preferences bullet, each General Tips paragraph (global, standing) and each topic of `What's in Memory`, which Codex groups under a named project scope. A topic MUST be filed under the `cwd:` recorded in the header of the rollout summary it points at, and global when it points at none or the header records none; its identity MUST name its scope, so a topic reads as task material the way a v1 task-group bullet does. While a v2 summary is there, the profile MUST come from v2 only, and v1's summary MUST yield only the preferences v2 does not state word for word.

#### Scenario: a Codex v2 topic reaches Claude Code once sorted into memory
- **GIVEN** Codex with only v2 memory, whose summary lists a topic pointing at a rollout summary recorded in a project checked out here, plus a preference and a General Tips paragraph
- **WHEN** memory syncs
- **THEN** the rules file holds the preference and the tip, and the topic waits to be sorted, written into no Claude Code memory
- **AND** once the topic is recorded as sorted into memory, the next sync writes it with its details into the marked block of that project's `MEMORY.md`

#### Scenario: with v2 beside it, v1's summary gives only what v2 does not say
- **GIVEN** v1 and v2 summaries with different profiles, one shared preference and one preference only v1 states
- **WHEN** the Codex reader reads the v1 summary
- **THEN** it yields only the preference v1 alone states
